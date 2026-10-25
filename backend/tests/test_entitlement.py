from datetime import timedelta

from sqlalchemy import select

from app.auth import EntitlementError, has_active_subscription, require_entitlement
from app.db import Entitlement, User


def _user(session) -> User:
    user = User(google_sub="sub-1", email="u@example.com")
    session.add(user)
    session.flush()
    return user


def _ent(session, user, active=True, expires_in_days=None) -> Entitlement:
    from datetime import datetime, timezone

    ent = Entitlement(
        user_id=user.id,
        product_id="history_audiobooks_monthly",
        active=active,
        expires_at=(datetime.now(timezone.utc) + timedelta(days=expires_in_days)) if expires_in_days is not None else None,
    )
    session.add(ent)
    session.flush()
    return ent


class TestHasActiveSubscription:
    def test_active_never_expiring(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=True)
        assert has_active_subscription(sqlite_session, user) is True

    def test_active_future_expiry(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=True, expires_in_days=7)
        assert has_active_subscription(sqlite_session, user) is True

    def test_inactive(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=False)
        assert has_active_subscription(sqlite_session, user) is False

    def test_expired(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=True, expires_in_days=-1)
        assert has_active_subscription(sqlite_session, user) is False

    def test_mixed_only_expired_and_inactive(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=False)
        _ent(sqlite_session, user, active=True, expires_in_days=-3)
        assert has_active_subscription(sqlite_session, user) is False

    def test_one_valid_among_expired(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=True, expires_in_days=-1)
        _ent(sqlite_session, user, active=True, expires_in_days=30)
        assert has_active_subscription(sqlite_session, user) is True

    def test_no_entitlements(self, sqlite_session):
        user = _user(sqlite_session)
        assert has_active_subscription(sqlite_session, user) is False


class TestRequireEntitlement:
    def test_returns_entitlement_when_active(self, sqlite_session):
        user = _user(sqlite_session)
        ent = _ent(sqlite_session, user, active=True)
        assert require_entitlement(sqlite_session, user).id == ent.id

    def test_raises_when_inactive(self, sqlite_session):
        user = _user(sqlite_session)
        _ent(sqlite_session, user, active=False)
        try:
            require_entitlement(sqlite_session, user)
            raise AssertionError("expected EntitlementError")
        except EntitlementError:
            pass

    def test_raises_when_no_entitlements(self, sqlite_session):
        user = _user(sqlite_session)
        try:
            require_entitlement(sqlite_session, user)
            raise AssertionError("expected EntitlementError")
        except EntitlementError:
            pass
