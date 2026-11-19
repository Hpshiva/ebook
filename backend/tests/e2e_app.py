"""The real app wired to the fake Apify providers, for the browser end-to-end test only.

Run with: uvicorn tests.e2e_app:app  (from the backend folder). Never deployed.
"""
from app import integrations
from app.core.config import config
from app.main import app  # noqa: F401  (the server imports this module's `app`)
from app.services import pipeline

from .fakes import FakeHashtagDiscovery, FakeProfiles, FakeReels

config.apify_token = "e2e-fake-token"
config.apify_token_from_env = True
pipeline.ApifyClient.limits = lambda self: {"limit_usd": 1000.0, "used_usd": 0.0, "remaining_usd": 1000.0}
pipeline.ApifyClient.prices = lambda self: {}

_discovery, _profiles, _reels = FakeHashtagDiscovery(), FakeProfiles(), FakeReels()
_real_discovery = integrations.get_discovery
integrations.get_discovery = lambda name: _discovery if name == "hashtag" else _real_discovery(name)
integrations.get_profile_provider = lambda name: _profiles if name == "apify" else None
integrations.get_reel_provider = lambda name: _reels if name == "apify" else None
