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


@pytest.fixture(autouse=True)
def fake_apify(request, monkeypatch):
    """Every test runs "live" against fake Apify providers: a token is set, the free
    allowance is large and prices are unknown, so no cost estimate is produced.
    Tests that check cost gating override these. Provider tests use the real client."""
    if request.module.__name__.endswith("test_providers"):
        return None
    from app import integrations
    from app.core import config as config_module
    from app.services import pipeline

    from .fakes import FakeHashtagDiscovery, FakeProfiles, FakeReels

    fakes = {"discovery": FakeHashtagDiscovery(), "profiles": FakeProfiles(), "reels": FakeReels()}
    monkeypatch.setattr(config_module.config, "apify_token", "test-token")
    monkeypatch.setattr(config_module.config, "apify_token_from_env", True)
    limits = {"limit_usd": 1000.0, "used_usd": 0.0, "remaining_usd": 1000.0}
    monkeypatch.setattr(pipeline.ApifyClient, "limits", lambda self: limits)
    monkeypatch.setattr(pipeline.ApifyClient, "prices", lambda self: {})
    real_discovery = integrations.get_discovery
    monkeypatch.setattr(integrations, "get_discovery",
                        lambda name: fakes["discovery"] if name == "hashtag" else real_discovery(name))
    monkeypatch.setattr(integrations, "get_profile_provider", lambda name: fakes["profiles"] if name == "apify" else None)
    monkeypatch.setattr(integrations, "get_reel_provider", lambda name: fakes["reels"] if name == "apify" else None)
    return fakes


def fake_search(client, niche="fitness", **extra):
    """A confirmed hashtag search against the fake providers."""
    res = client.post("/api/discovery/run", json={"discovery_source": "hashtag", "profile_provider": "apify",
                                                  "niche": niche, "confirmed": True, **extra})
    assert res.status_code == 200, res.text
    return res.json()["run"]
