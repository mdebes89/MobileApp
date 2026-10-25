"""Google ID token verification and subscription entitlement checks."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Entitlement, User

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


class EntitlementError(Exception):
    pass


def verify_google_id_token(id_token: str) -> dict:
    """Verify a Google Sign-In ID token. Returns the decoded claims dict."""
    settings = get_settings()
    try:
        from google.auth.transport import requests as grequests
        from google.oauth2 import id_token as gid_token

        decoded = gid_token.verify_oauth2_token(id_token, grequests.Request())
    except ImportError as exc:
        raise AuthError("google-auth library not installed") from exc
    except ValueError as exc:
        raise AuthError(f"invalid ID token: {exc}") from exc

    allowed = settings.google_client_id_list
    if allowed and decoded.get("aud") not in allowed:
        raise AuthError("token audience does not match configured client IDs")
    if decoded.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise AuthError("invalid token issuer")
    return decoded


def get_or_create_user(session: Session, claims: dict) -> User:
    sub = claims["sub"]
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = User(
            google_sub=sub,
            email=claims.get("email", ""),
            display_name=claims.get("name"),
        )
        session.add(user)
        session.flush()
    return user


def has_active_subscription(session: Session, user: User) -> bool:
    """An active entitlement must be marked active and not expired."""
    now = datetime.now(timezone.utc)
    for ent in user.entitlements:
        if not ent.active:
            continue
        if ent.expires_at is not None:
            exp = ent.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                continue
        return True
    return False


def require_entitlement(session: Session, user: User) -> Entitlement:
    now = datetime.now(timezone.utc)
    active = [
        e
        for e in user.entitlements
        if e.active and (e.expires_at is None or (e.expires_at if e.expires_at.tzinfo else e.expires_at.replace(tzinfo=timezone.utc)) > now)
    ]
    if not active:
        raise EntitlementError("no active subscription entitlement")
    return active[0]
