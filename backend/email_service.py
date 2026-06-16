import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST     = os.getenv("SMTP_HOST", "")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "") or SMTP_USER
APP_URL       = os.getenv("APP_URL", "https://velostats.app")


def _send(to: str, subject: str, html: str, plain: str):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        raise RuntimeError("SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = to
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_FROM, to, msg.as_string())


def send_email_verification(to_email: str, username: str, token: str, expires_at):
    verify_url  = f"{APP_URL}/verify-email?token={token}"
    expires_str = f"{expires_at.day} {expires_at.strftime('%B %Y at %H:%M')} UTC"
    subject     = "Verify your new email — VeloStats"

    plain = f"""Hi {username},

You requested to change your VeloStats email address to this address.

Click the link below to confirm:
{verify_url}

This link expires on {expires_str}.

If you did not request this change, you can safely ignore this email.

The VeloStats Team
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#09090f;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#09090f;padding:48px 16px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#0f0f1a;border-radius:16px;border:1px solid #1e1e38;overflow:hidden;">
        <tr>
          <td style="padding:32px 40px 24px;border-bottom:1px solid #1e1e38;">
            <span style="font-size:20px;font-weight:800;letter-spacing:0.1em;color:#f0f0ff;">VELO</span><span style="font-size:20px;font-weight:800;letter-spacing:0.1em;color:#c8ff00;">STATS</span>
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px;">
            <p style="margin:0 0 8px;font-size:13px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#c8ff00;">Email verification</p>
            <h1 style="margin:0 0 24px;font-size:28px;font-weight:800;line-height:1.2;color:#f0f0ff;">Confirm your new email</h1>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.7;color:#8888aa;">
              Hi <strong style="color:#f0f0ff;">{username}</strong>,<br><br>
              Click the button below to verify <strong style="color:#f0f0ff;">{to_email}</strong> as your new VeloStats email address.
            </p>
            <table cellpadding="0" cellspacing="0" style="margin:0 0 28px;">
              <tr>
                <td style="background:#c8ff00;border-radius:10px;">
                  <a href="{verify_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;color:#09090f;text-decoration:none;">
                    Verify email address →
                  </a>
                </td>
              </tr>
            </table>
            <div style="background:#1a1a2e;border:1px solid #ffffff15;border-radius:8px;padding:12px 16px;margin-bottom:20px;">
              <p style="margin:0;font-size:12px;color:#8888aa;">Link expires on <strong style="color:#f0f0ff;">{expires_str}</strong></p>
            </div>
            <p style="margin:0;font-size:13px;color:#3a3a5a;">If you didn't request this change, you can safely ignore this email — your current address will remain unchanged.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 40px;border-top:1px solid #1e1e38;">
            <p style="margin:0;font-size:12px;color:#3a3a5a;">© {__import__('datetime').date.today().year} VeloStats</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    _send(to_email, subject, html, plain)


def send_lifetime_offer(to_email: str, username: str, token: str, expires_at):
    offer_url   = f"{APP_URL}/lifetime-offer?token={token}"
    expires_str = f"{expires_at.day} {expires_at.strftime('%B %Y at %H:%M')} UTC"

    subject = "A special offer, just for you — VeloStats Lifetime"

    plain = f"""Hi {username},

You've been personally selected for a special offer.

Unlock VeloStats Lifetime access for a one-time payment of just €129.
That's full Pro access — AI coaching, unlimited activities, training plans — forever, with no future charges.

This offer is exclusive to you and expires on {expires_str}.

Claim your offer: {offer_url}

This offer was sent personally by the VeloStats team.

Ride fast,
The VeloStats Team
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#09090f;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#09090f;padding:48px 16px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#0f0f1a;border-radius:16px;border:1px solid #1e1e38;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="padding:32px 40px 24px;border-bottom:1px solid #1e1e38;">
            <span style="font-size:20px;font-weight:800;letter-spacing:0.1em;color:#f0f0ff;">VELO</span><span style="font-size:20px;font-weight:800;letter-spacing:0.1em;color:#c8ff00;">STATS</span>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 32px;">
            <p style="margin:0 0 8px;font-size:13px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#c8ff00;">Special offer</p>
            <h1 style="margin:0 0 24px;font-size:32px;font-weight:800;line-height:1.15;color:#f0f0ff;">
              A special offer,<br>just for you.
            </h1>
            <p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:#8888aa;">
              Hi <strong style="color:#f0f0ff;">{username}</strong>,
            </p>
            <p style="margin:0 0 24px;font-size:15px;line-height:1.7;color:#8888aa;">
              You've been personally selected for something we don't offer publicly.<br><br>
              Unlock <strong style="color:#f0f0ff;">VeloStats Lifetime</strong> access for a one-time payment of
              <strong style="color:#c8ff00;font-size:18px;">€129</strong> — full Pro features,
              AI coaching, unlimited activities and training plans, forever. No subscriptions, no future charges.
            </p>

            <!-- Expiry notice -->
            <div style="background:#1a1a2e;border:1px solid #ff4d6d40;border-radius:8px;padding:12px 16px;margin:0 0 28px;">
              <p style="margin:0;font-size:13px;color:#ff4d6d;font-weight:600;">
                ⏰ This offer expires on {expires_str}
              </p>
            </div>

            <!-- CTA -->
            <table cellpadding="0" cellspacing="0" style="margin:0 0 32px;">
              <tr>
                <td style="background:#c8ff00;border-radius:10px;">
                  <a href="{offer_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;color:#09090f;text-decoration:none;letter-spacing:0.02em;">
                    Claim your offer →
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:0;font-size:13px;line-height:1.6;color:#3a3a5a;">
              This offer is exclusive to you and is not available to the general public.<br>
              If you did not expect this email, you can safely ignore it.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 40px;border-top:1px solid #1e1e38;">
            <p style="margin:0;font-size:12px;color:#3a3a5a;">
              © {__import__('datetime').date.today().year} VeloStats · Built for riders who want more.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    _send(to_email, subject, html, plain)
