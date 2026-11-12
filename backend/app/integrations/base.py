"""Provider interfaces. New paid or official sources plug in here without touching the app."""
from __future__ import annotations

from dataclasses import dataclass, field


class ProviderError(Exception):
    """A provider failed in a way the user should see."""


class ProviderAuthError(ProviderError):
    pass


class FreeAllowanceExhausted(ProviderError):
    pass


@dataclass
class Handle:
    username: str
    source: str
    title: str = ""
    snippet: str = ""
    est_followers: int | None = None
    est_views: int | None = None  # plays of the reel that surfaced this creator, when known


@dataclass
class DiscoveryResult:
    handles: list[Handle] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    actor_runs: int = 0
    actual_cost_usd: float | None = None  # only for paid discovery sources


@dataclass
class FetchResult:
    profiles: list[dict] = field(default_factory=list)  # raw provider payloads
    failed: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    actor_runs: int = 0
    actual_cost_usd: float | None = None  # only when the provider reports it


class DiscoveryProvider:
    name = "base"
    is_external = False

    def discover(self, params: dict, limit: int) -> DiscoveryResult:  # pragma: no cover
        raise NotImplementedError


class ProfileProvider:
    name = "base"
    is_external = False

    def fetch(self, usernames: list[str]) -> FetchResult:  # pragma: no cover
        raise NotImplementedError
