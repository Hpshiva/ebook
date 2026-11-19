from __future__ import annotations

from ..core.config import config
from .apify_provider import ApifyHashtagDiscovery, ApifyProfiles, ApifyReels
from .base import DiscoveryProvider, ProfileProvider, ProviderError
from .search_discovery import DuckDuckGoDiscovery, ManualDiscovery

DISCOVERY_SOURCES = {"duckduckgo": DuckDuckGoDiscovery, "manual": ManualDiscovery}
PROFILE_PROVIDERS = ("apify", "none")


def get_discovery(name: str) -> DiscoveryProvider:
    if name == "hashtag":
        return ApifyHashtagDiscovery(config.apify_token)
    if name not in DISCOVERY_SOURCES:
        raise ProviderError(f"Unknown discovery source: {name}")
    return DISCOVERY_SOURCES[name]()


def get_profile_provider(name: str) -> ProfileProvider | None:
    if name == "apify":
        return ApifyProfiles(config.apify_token)
    if name == "none":
        return None
    raise ProviderError(f"Unknown profile provider: {name}")


def get_reel_provider(name: str):
    """Second-stage provider for reel play counts."""
    return ApifyReels(config.apify_token) if name == "apify" else None
