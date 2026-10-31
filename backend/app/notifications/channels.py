"""External notification channels: email (SMTP or Brevo), SMS (Twilio), browser push (Web Push).

Each channel is active only when its settings are present; nothing is claimed as
sent unless the provider accepted it. Every attempt is recorded in
notification_deliveries with its outcome.
"""
from __future__ import annotations

import json
import logging
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from app.core.config import get_settings

log = logging.getLogger("civicconnect.notifications")


class ChannelError(Exception):
    pass


class SubscriptionGone(ChannelError):
    """The push endpoint no longer exists; the subscription should be deleted."""


def _subject(message: str) -> str:
    return "CivicConnect update"


def _email_body(message: str, link: str | None) -> tuple[str, str]:
    text = f"{message}\n\n" + (f"View it here: {link}\n\n" if link else "") + \
        "You can turn off email notifications in your CivicConnect profile."
    html = (
        f"<p>{_esc(message)}</p>"
        + (f'<p><a href="{_esc(link)}">View your complaint</a></p>' if link else "")
        + '<p style="color:#64748b;font-size:12px">You can turn off email notifications in your CivicConnect profile.</p>'
    )
    return text, html


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------- email ----------------
def email_provider() -> str | None:
    s = get_settings()
    p = s.EMAIL_PROVIDER.lower()
    if p == "smtp" and s.SMTP_HOST and s.EMAIL_FROM:
        return "smtp"
    if p == "brevo" and s.BREVO_API_KEY and s.EMAIL_FROM:
        return "brevo"
    return None


def send_email(to: str, name: str, message: str, link: str | None) -> str:
    s = get_settings()
    provider = email_provider()
    text, html = _email_body(message, link)
    if provider == "smtp":
        msg = EmailMessage()
        msg["Subject"] = _subject(message)
        msg["From"] = f"{s.EMAIL_FROM_NAME} <{s.EMAIL_FROM}>"
        msg["To"] = to
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
        try:
            if s.SMTP_USE_SSL:
                with smtplib.SMTP_SSL(s.SMTP_HOST, s.SMTP_PORT, context=ssl.create_default_context(), timeout=20) as srv:
                    if s.SMTP_USERNAME:
                        srv.login(s.SMTP_USERNAME, s.SMTP_PASSWORD)
                    srv.send_message(msg)
            else:
                with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=20) as srv:
                    srv.starttls(context=ssl.create_default_context())
                    if s.SMTP_USERNAME:
                        srv.login(s.SMTP_USERNAME, s.SMTP_PASSWORD)
                    srv.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            raise ChannelError(f"smtp: {type(exc).__name__}")
        return "smtp"
    if provider == "brevo":
        try:
            r = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": s.BREVO_API_KEY, "accept": "application/json"},
                json={"sender": {"email": s.EMAIL_FROM, "name": s.EMAIL_FROM_NAME}, "to": [{"email": to, "name": name}],
                      "subject": _subject(message), "textContent": text, "htmlContent": html},
                timeout=20,
            )
        except httpx.HTTPError as exc:
            raise ChannelError(f"brevo: {type(exc).__name__}")
        if r.status_code >= 300:
            raise ChannelError(f"brevo: HTTP {r.status_code}")
        return "brevo"
    raise ChannelError("email not configured")


# ---------------- SMS ----------------
def sms_provider() -> str | None:
    s = get_settings()
    if s.SMS_PROVIDER.lower() == "twilio" and s.TWILIO_ACCOUNT_SID and s.TWILIO_AUTH_TOKEN and s.TWILIO_FROM_NUMBER:
        return "twilio"
    return None


def send_sms(to: str, message: str) -> str:
    s = get_settings()
    if sms_provider() != "twilio":
        raise ChannelError("sms not configured")
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{s.TWILIO_ACCOUNT_SID}/Messages.json",
            auth=(s.TWILIO_ACCOUNT_SID, s.TWILIO_AUTH_TOKEN),
            data={"From": s.TWILIO_FROM_NUMBER, "To": to, "Body": message[:600]},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ChannelError(f"twilio: {type(exc).__name__}")
    if r.status_code >= 300:
        raise ChannelError(f"twilio: HTTP {r.status_code}")
    return "twilio"


# ---------------- browser push ----------------
def push_configured() -> bool:
    s = get_settings()
    return bool(s.VAPID_PUBLIC_KEY and s.VAPID_PRIVATE_KEY and s.VAPID_SUBJECT)


def send_push(endpoint: str, p256dh: str, auth: str, message: str, link: str | None) -> str:
    s = get_settings()
    if not push_configured():
        raise ChannelError("push not configured")
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=json.dumps({"title": "CivicConnect", "body": message, "url": link or "/notifications"}),
            vapid_private_key=s.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": s.VAPID_SUBJECT},
            timeout=20,
        )
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):
            raise SubscriptionGone("push: subscription expired")
        raise ChannelError(f"push: HTTP {status}")
    except Exception as exc:  # network errors from requests
        raise ChannelError(f"push: {type(exc).__name__}")
    return "webpush"


def channel_status() -> dict:
    return {
        "in_app": True,
        "email": email_provider(),
        "sms": sms_provider(),
        "push": "webpush" if push_configured() else None,
    }
