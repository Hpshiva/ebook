"""Environment-driven configuration. Secrets never live in code."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR.parent / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _secret_key() -> str:
    """Use SECRET_KEY from the environment, else a persistent locally generated one."""
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    path = BACKEND_DIR / "data" / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    path.chmod(0o600)
    return key


class Config:
    # "or" (not a getenv default) so an empty line in .env falls back to the default too.
    database_url: str = os.getenv("DATABASE_URL") or f"sqlite:///{BACKEND_DIR / 'data' / 'creator_finder.db'}"
    secret_key: str = _secret_key()
    token_minutes: int = int(os.getenv("TOKEN_MINUTES") or "720")
    apify_token: str = os.getenv("APIFY_TOKEN", "")
    cors_origins: list[str] = [
        o.strip() for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()
    ]


config = Config()

# Defaults for settings that users can edit in the app (stored in the DB).
DEFAULT_SETTINGS: dict = {
    "filters": {
        "min_followers": 10_000,
        "max_followers": 100_000,
        "min_views": 50_000,
        "max_views": 200_000,
        "min_reels": 2,
        "require_email": True,
        # With require_email on: True sends creators without an email to Needs review
        # (to contact by Instagram message); False rejects them.
        "no_email_to_review": True,
        "require_public": True,
        "exclude_selling": True,
    },
    "scoring_weights": {
        "follower_fit": 10,
        "reel_views": 25,
        "engagement": 20,
        "niche_relevance": 20,
        "selling_status": 15,
        "contact": 10,
    },
    "cache_days": 14,
    "max_profiles_per_search": 50,
    "collect_phone": False,
    # "mock" keeps every call local and free. "live" allows external providers
    # (still gated by an explicit confirmation on every search).
    "provider_mode": "mock",
    "monthly_budget_inr": 0,
    "budget_warn_pct": 80,
    "fx": {"usd_inr": 90.0, "updated_at": None, "source": "manual default, please update"},
    # Not a fact baked into code: refreshed from Apify's own pricing API and from
    # observed run costs. None means "unknown, cannot estimate".
    "apify_pricing": {"usd_per_profile": None, "usd_per_reel": None, "usd_per_reel_run": None,
                      "usd_per_hashtag_result": None,
                      "source": None, "updated_at": None},
    # Reels fetched per creator in the second stage (only for creators that pass the cheap checks).
    "reels_per_creator": 5,
    "sender_name": "",
}
