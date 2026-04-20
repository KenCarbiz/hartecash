import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fsbo.api.main import app
from fsbo.db import get_session
from fsbo.models import Base


@pytest.fixture
def db_session():
    # StaticPool + single shared connection so the in-memory SQLite DB
    # keeps its schema across every call within the test.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    # autoflush=True for tests so state added in one request is visible to
    # subsequent requests that share this session via the dependency override.
    SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
