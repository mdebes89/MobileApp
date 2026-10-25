from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_engine = None
_SessionFactory: sessionmaker | None = None


def get_engine():
    global _engine, _SessionFactory
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory


class session_scope:
    """Context manager providing a session committed on success, rolled back on error."""

    def __init__(self, engine=None):
        self.factory = get_session_factory()
        self.session = None

    def __enter__(self):
        self.session = self.factory()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
        return False
