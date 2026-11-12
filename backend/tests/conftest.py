"""Tests run on an in-memory database and never touch the network or any paid API."""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-anywhere-else-0123456789"
os.environ["APIFY_TOKEN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import auth as auth_api  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_api._failures.clear()
    yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if any test tries a real HTTP call."""
    import requests

    def blocked(*args, **kwargs):
        raise AssertionError("Network access attempted in a test")

    monkeypatch.setattr(requests.Session, "request", blocked)
    monkeypatch.setattr(requests.Session, "post", blocked)


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def anon():
    return TestClient(app)


@pytest.fixture
def client(anon):
    """Signed in as the administrator."""
    res = anon.post("/api/auth/setup", json={"email": "admin@test.local", "name": "Admin", "password": PASSWORD})
    assert res.status_code == 200, res.text
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {res.json()['token']}"
    return c


def login_as(email: str) -> TestClient:
    c = TestClient(app)
    res = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    c.headers["Authorization"] = f"Bearer {res.json()['token']}"
    return c


def demo_search(client, niche="fitness", **extra):
    res = client.post("/api/discovery/run", json={"discovery_source": "demo", "profile_provider": "demo",
                                                  "niche": niche, **extra})
    assert res.status_code == 200, res.text
    return res.json()["run"]
