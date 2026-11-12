from __future__ import annotations

from ..core.config import config
from .apify_provider import ApifyHashtagDiscovery, ApifyProfiles, ApifyReels
from .base import DiscoveryProvider, ProfileProvider, ProviderError
from .mock_provider import MockDiscovery, MockProfiles
from .search_discovery import DuckDuckGoDiscovery, ManualDiscovery

DISCOVERY_SOURCES = {"demo": MockDiscovery, "duckduckgo": DuckDuckGoDiscovery, "manual": ManualDiscovery}
PROFILE_PROVIDERS = ("demo", "apify", "none")


def get_discovery(name: str) -> DiscoveryProvider:
    if name not in DISCOVERY_SOURCES and name != "hashtag":
        raise ProviderError(f"Unknown discovery source: {name}")
    if name == "hashtag":
        return ApifyHashtagDiscovery(config.apify_token)
    return DISCOVERY_SOURCES[name]()


def get_profile_provider(name: str) -> ProfileProvider | None:
    if name == "demo":
        return MockProfiles()
    if name == "apify":
        return ApifyProfiles(config.apify_token)
    if name == "none":
        return None
    raise ProviderError(f"Unknown profile provider: {name}")


def get_reel_provider(name: str):
    """Second-stage provider for reel play counts. Demo profiles already carry them."""
    return ApifyReels(config.apify_token) if name == "apify" else None
