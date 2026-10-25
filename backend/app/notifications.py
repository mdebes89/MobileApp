import logging

from app.config import get_settings

log = logging.getLogger(__name__)


def push_audiobook_ready(device_token: str, audiobook_id: str, title: str) -> bool:
    """Send an FCM push. No-op (logged) when Firebase credentials are not configured."""
    settings = get_settings()
    if not (settings.fcm_enabled and settings.fcm_credentials_json and device_token):
        log.info("FCM disabled or token missing; would push audiobook=%s to device", audiobook_id)
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            creds = credentials.Cert(settings.fcm_credentials_json)
            firebase_admin.initialize_app(creds)
        message = messaging.Message(
            data={"audiobook_id": audiobook_id, "title": title, "type": "audiobook_ready"},
            android=messaging.AndroidConfig(priority="high"),
            token=device_token,
        )
        messaging.send(message)
        return True
    except Exception:
        log.exception("FCM push failed for audiobook=%s", audiobook_id)
        return False
