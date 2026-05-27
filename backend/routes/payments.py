import os
import stripe
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db
import models
from auth import get_current_user

log = logging.getLogger(__name__)

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
APP_URL        = os.getenv("APP_URL", "http://localhost:5173")

PRICE_IDS = {
    "pro":      os.getenv("STRIPE_PRICE_PRO", ""),
    "annual":   os.getenv("STRIPE_PRICE_ANNUAL", ""),
    "lifetime": os.getenv("STRIPE_PRICE_LIFETIME", ""),
}


# ── Checkout ──────────────────────────────────────────────────────────────────

@router.post("/create-checkout")
def create_checkout(body: dict, current_user=Depends(get_current_user)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payments are not configured yet.")

    tier = body.get("tier", "")
    if tier not in PRICE_IDS or not PRICE_IDS[tier]:
        raise HTTPException(status_code=400, detail=f"Unknown or unconfigured plan: {tier}")

    mode = "payment" if tier == "lifetime" else "subscription"

    session = stripe.checkout.Session.create(
        customer_email=current_user.email or None,
        payment_method_types=["card"],
        line_items=[{"price": PRICE_IDS[tier], "quantity": 1}],
        mode=mode,
        metadata={"user_id": str(current_user.id), "tier": tier},
        success_url=f"{APP_URL}/settings?upgraded=1",
        cancel_url=f"{APP_URL}/settings",
    )
    return {"url": session.url}


# ── Lifetime offer (token-gated) ─────────────────────────────────────────────

@router.get("/validate-offer")
def validate_offer(token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.offer_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid offer link.")
    if user.offer_expires_at and user.offer_expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This offer has expired.")
    return {
        "valid":      True,
        "username":   user.username,
        "expires_at": user.offer_expires_at.isoformat() if user.offer_expires_at else None,
    }


@router.post("/lifetime-checkout")
def lifetime_checkout(body: dict, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payments are not configured yet.")
    token = body.get("token", "")
    user  = db.query(models.User).filter(models.User.offer_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid offer link.")
    if user.offer_expires_at and user.offer_expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This offer has expired.")
    if user.id != current_user.id:
        raise HTTPException(status_code=403, detail="This offer belongs to a different account. Please log in with the correct account.")
    if not PRICE_IDS.get("lifetime"):
        raise HTTPException(status_code=503, detail="Lifetime plan is not configured yet.")

    session = stripe.checkout.Session.create(
        customer_email=current_user.email or None,
        payment_method_types=["card"],
        line_items=[{"price": PRICE_IDS["lifetime"], "quantity": 1}],
        mode="payment",
        metadata={"user_id": str(current_user.id), "tier": "lifetime", "offer_token": token},
        success_url=f"{APP_URL}/settings?upgraded=1",
        cancel_url=f"{APP_URL}/lifetime-offer?token={token}",
    )
    return {"url": session.url}


# ── Webhook ───────────────────────────────────────────────────────────────────

def _utc(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except Exception as e:
        log.error("Webhook signature error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_dict = event.to_dict()
    etype = event_dict["type"]
    data  = event_dict["data"]["object"]
    log.info("Webhook received: %s", etype)

    try:
        if etype == "checkout.session.completed":
            metadata = data.get("metadata") or {}
            user_id  = metadata.get("user_id")
            tier     = metadata.get("tier")

            if not user_id or not tier:
                log.warning("checkout.session.completed missing metadata: %s", metadata)
                return {"ok": True}

            user = db.query(models.User).filter(models.User.id == int(user_id)).first()
            if not user:
                log.warning("checkout.session.completed: user %s not found", user_id)
                return {"ok": True}

            user.membership         = tier
            user.subscription_start = datetime.utcnow()
            user.stripe_customer_id = data.get("customer")

            if tier == "lifetime":
                user.subscription_end = None
            else:
                sub_id = data.get("subscription")
                if sub_id:
                    sub = stripe.Subscription.retrieve(sub_id)
                    period_end = getattr(sub, "current_period_end", None)
                    if period_end:
                        user.subscription_end = _utc(period_end)

            if tier == "lifetime":
                user.offer_token      = None
                user.offer_expires_at = None

            db.commit()
            log.info("User %s upgraded to %s", user_id, tier)

        elif etype == "invoice.payment_succeeded":
            customer_id = data.get("customer")
            sub_id      = data.get("subscription")
            if customer_id and sub_id:
                user = db.query(models.User).filter(models.User.stripe_customer_id == customer_id).first()
                if user and user.membership in ("pro", "annual"):
                    sub = stripe.Subscription.retrieve(sub_id)
                    period_end = getattr(sub, "current_period_end", None)
                    if period_end:
                        user.subscription_end = _utc(period_end)
                    db.commit()

        elif etype == "customer.subscription.deleted":
            customer_id = data.get("customer")
            if customer_id:
                user = db.query(models.User).filter(models.User.stripe_customer_id == customer_id).first()
                if user and user.membership in ("pro", "annual"):
                    user.membership       = "free"
                    user.subscription_end = None
                    db.commit()

    except Exception as e:
        log.error("Webhook handler error for %s: %s", etype, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": True}
