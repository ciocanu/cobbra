"""Feature access: whether paid plans exist on this instance, and who gets full access.

With PAYMENTS_ENABLED unset (the default), every account gets every feature and the
Stripe routes are not mounted. AI features are still capped by utils/ai_budget.py.
"""

import os


def payments_enabled() -> bool:
    return os.getenv("PAYMENTS_ENABLED", "false").lower() == "true"


def has_full_access(user) -> bool:
    """True when the user can use features that were Pro-only under paid plans."""
    return not payments_enabled() or (user.membership or "free") != "free"
