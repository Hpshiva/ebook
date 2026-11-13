"""The Apify token can be saved inside the app by an admin. It must never be exposed."""
from app.api import reports
from app.core import config as config_module
from app.integrations.base import ProviderAuthError
from app.models import Setting
from app.services import pipeline

from .conftest import PASSWORD, login_as

TOKEN = "apify_api_" + "x" * 38
LIMITS = {"limit_usd": 5.0, "used_usd": 1.0, "remaining_usd": 4.0}


def _reset_token_state(monkeypatch):
    cfg = config_module.config
    for name, value in (("apify_token", ""), ("apify_token_from_env", False), ("apify_token_from_app", False)):
        monkeypatch.setattr(cfg, name, value)  # restored after the test
    return cfg


def _rejects(self):
    raise ProviderAuthError("bad token")


def test_admin_can_save_the_token_and_it_is_never_exposed(client, db, monkeypatch):
    cfg = _reset_token_state(monkeypatch)
    assert client.get("/api/settings").json()["apify_token_configured"] is False

    monkeypatch.setattr(reports.ApifyClient, "limits", _rejects)
    assert client.put("/api/settings/apify-token", json={"token": TOKEN}).status_code == 400
    assert client.put("/api/settings/apify-token", json={"token": "short"}).status_code == 422
    assert db.get(Setting, "_apify_token") is None

    monkeypatch.setattr(reports.ApifyClient, "limits", lambda self: LIMITS)
    saved = client.put("/api/settings/apify-token", json={"token": TOKEN})
    body = saved.json()
    assert saved.status_code == 200 and body["apify_token_configured"] is True
    assert body["apify_token_source"] == "saved in the app" and body["apify_limits"]["remaining_usd"] == 4.0
    for res in (saved, client.get("/api/settings"), client.get("/api/costs"), client.get("/api/audit"), client.get("/api/health")):
        assert TOKEN not in res.text
    assert client.put("/api/settings", json={"sender_name": "x"}).status_code == 200  # ordinary settings do not disturb it
    db.expire_all()
    assert db.get(Setting, "_apify_token").value == TOKEN

    # A fresh server instance (empty memory) picks the token up from the database.
    monkeypatch.setattr(cfg, "apify_token", "")
    monkeypatch.setattr(cfg, "apify_token_from_app", False)
    client.put("/api/settings", json={"provider_mode": "live"})
    monkeypatch.setattr(pipeline.ApifyClient, "limits", lambda self: LIMITS)
    monkeypatch.setattr(pipeline.ApifyClient, "prices", lambda self: {
        "usd_per_profile": 0.004, "usd_per_reel": 0.002, "usd_per_reel_run": 0.001, "usd_per_hashtag_result": 0.003})
    search = {"discovery_source": "manual", "profile_provider": "apify", "usernames": "a"}
    gate = client.post("/api/discovery/run", json=search).json()
    assert gate["allowed"] is True and cfg.apify_token == TOKEN

    gone = client.delete("/api/settings/apify-token").json()
    assert gone["apify_token_configured"] is False and cfg.apify_token == ""
    gate = client.post("/api/discovery/run", json=search).json()
    assert gate["allowed"] is False and "APIFY_TOKEN is not configured" in gate["reasons"][0]
    actions = [a["action"] for a in client.get("/api/audit").json()]
    assert "apify_token.save" in actions and "apify_token.remove" in actions


def test_only_an_admin_can_change_the_token_and_an_environment_token_wins(client, monkeypatch):
    _reset_token_state(monkeypatch)
    client.post("/api/users", json={"email": "staff@test.local", "name": "Staff", "password": PASSWORD, "role": "staff"})
    staff = login_as("staff@test.local")
    assert staff.put("/api/settings/apify-token", json={"token": TOKEN}).status_code == 403
    assert staff.delete("/api/settings/apify-token").status_code == 403
    monkeypatch.setattr(config_module.config, "apify_token_from_env", True)
    assert client.put("/api/settings/apify-token", json={"token": TOKEN}).status_code == 409
