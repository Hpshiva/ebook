"""Apify "apify/instagram-profile-scraper" through the official Apify API.

Uses the asynchronous run -> poll -> fetch dataset workflow with retries and
exponential backoff. Cost comes from what Apify reports for the run
(usageTotalUsd); nothing here assumes a fixed price per profile.
"""
from __future__ import annotations

import logging
import time

import requests

from .base import DiscoveryProvider, DiscoveryResult, FetchResult, Handle, FreeAllowanceExhausted, ProfileProvider, ProviderAuthError, ProviderError

log = logging.getLogger("creator_finder.apify")
API = "https://api.apify.com/v2"
ACTOR = "apify~instagram-profile-scraper"
# The profile Actor does not return reel view counts (confirmed on a live run,
# 12 Nov 2026), so reel plays come from Apify's separate reel Actor.
REEL_ACTOR = "apify~instagram-reel-scraper"
HASHTAG_ACTOR = "apify~instagram-hashtag-scraper"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyClient:
    def __init__(self, token: str, session: requests.Session | None = None, sleep=time.sleep, max_retries: int = 4):
        self.token = token
        self.http = session or requests.Session()
        self.sleep = sleep
        self.max_retries = max_retries

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        headers = {"Authorization": f"Bearer {self.token}"}
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self.http.request(method, f"{API}{path}", headers=headers, timeout=90, **kwargs)
            except requests.RequestException as exc:  # timeouts, connection errors
                last = ProviderError(f"Apify network error: {type(exc).__name__}")
            else:
                if resp.status_code in (401, 403):
                    raise ProviderAuthError("Apify rejected the API token. Check APIFY_TOKEN.")
                if resp.status_code == 402:
                    raise FreeAllowanceExhausted("Apify's free allowance for this month is used up.")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = ProviderError(f"Apify returned HTTP {resp.status_code}")
                elif resp.status_code >= 400:
                    raise ProviderError(f"Apify returned HTTP {resp.status_code}")
                else:
                    try:
                        return resp.json()
                    except ValueError:
                        raise ProviderError("Apify returned a response that is not valid JSON") from None
            self.sleep(min(2 ** attempt, 30))
        raise last or ProviderError("Apify request failed")

    def limits(self) -> dict | None:
        """Monthly usage vs. limit for the account (the free plan's credit shows up here)."""
        try:
            data = self._request("GET", "/users/me/limits").get("data", {})
        except ProviderAuthError:
            raise
        except ProviderError:
            return None
        limit = (data.get("limits") or {}).get("maxMonthlyUsageUsd")
        used = (data.get("current") or {}).get("monthlyUsageUsd")
        if limit is None or used is None:
            return None
        return {"limit_usd": float(limit), "used_usd": round(float(used), 4),
                "remaining_usd": round(max(0.0, float(limit) - float(used)), 4)}

    def event_prices(self, actor: str) -> dict[str, float]:
        """The Actor's own published price per charge event. Empty if it cannot be read."""
        try:
            data = self._request("GET", f"/acts/{actor}").get("data", {})
        except ProviderAuthError:
            raise
        except ProviderError:
            return {}
        infos = data.get("pricingInfos") or []
        if not infos:
            return {}
        info = infos[-1]
        if info.get("pricingModel") == "PRICE_PER_DATASET_ITEM" and info.get("pricePerUnitUsd") is not None:
            return {"item": float(info["pricePerUnitUsd"])}
        out: dict[str, float] = {}
        for key, event in (((info.get("pricingPerEvent") or {}).get("actorChargeEvents")) or {}).items():
            price = event.get("eventPriceUsd")
            if price is None:  # tiered pricing: the free tier is the most expensive, so it is the safe estimate
                price = ((event.get("eventTieredPricingUsd") or {}).get("FREE") or {}).get("tieredEventPriceUsd")
            if price is not None:
                out[key] = float(price)
        return out

    def current_price_per_profile(self) -> float | None:
        prices = self.event_prices(ACTOR)
        return prices.get("profile", prices.get("item", prices.get("result")))

    def prices(self) -> dict:
        """Prices needed for an estimate: per profile, per reel, and per reel run."""
        reel = self.event_prices(REEL_ACTOR)
        tag = self.event_prices(HASHTAG_ACTOR)
        return {"usd_per_profile": self.current_price_per_profile(),
                "usd_per_reel": reel.get("reel", reel.get("item")),
                "usd_per_reel_run": reel.get("actor-start", 0.0) if reel else None,
                "usd_per_hashtag_result": tag.get("result", tag.get("item"))}

    def settled_cost(self, run_id: str, first: float | None, tries: int = 5, pause: float = 5) -> float | None:
        """Apify posts pay-per-event charges a few seconds after a run finishes
        (seen live: $0.001 at finish, $0.0088 ten seconds later). Wait for the figure to settle."""
        last, stable = first, 0
        for _ in range(tries):
            self.sleep(pause)
            try:
                cost = self._request("GET", f"/actor-runs/{run_id}").get("data", {}).get("usageTotalUsd")
            except ProviderError:
                break
            cost = float(cost) if isinstance(cost, (int, float)) else None
            if cost is not None and last is not None and abs(cost - last) < 1e-9:
                stable += 1
                if stable >= 2 or cost != first:
                    return cost
            else:
                stable = 0
            last = cost if cost is not None else last
        return last

    def run(self, usernames: list[str], poll_seconds: int = 30, max_wait: int = 900, actor: str = ACTOR,
            payload: dict | None = None) -> tuple[list, float | None]:
        run = self._request("POST", f"/acts/{actor}/runs", params={"waitForFinish": poll_seconds},
                            json=payload if payload is not None else {"usernames": usernames}).get("data", {})
        run_id, waited = run.get("id"), poll_seconds
        if not run_id:
            raise ProviderError("Apify did not return a run id")
        while run.get("status") not in TERMINAL:
            if waited >= max_wait:
                raise ProviderError("Apify run timed out before finishing")
            run = self._request("GET", f"/actor-runs/{run_id}", params={"waitForFinish": poll_seconds}).get("data", {})
            waited += poll_seconds
        if run.get("status") != "SUCCEEDED":
            raise ProviderError(f"Apify run ended with status {run.get('status')}")
        items = self._request("GET", f"/datasets/{run.get('defaultDatasetId')}/items", params={"clean": "true"})
        cost = run.get("usageTotalUsd")
        cost = self.settled_cost(run_id, float(cost) if isinstance(cost, (int, float)) else None)
        return (items if isinstance(items, list) else []), cost


class ApifyProfiles(ProfileProvider):
    name = "apify"
    is_external = True

    def __init__(self, token: str, client: ApifyClient | None = None, batch_size: int = 25):
        if not token and client is None:
            raise ProviderAuthError("APIFY_TOKEN is not set.")
        self.client = client or ApifyClient(token)
        self.batch_size = batch_size

    def fetch(self, usernames: list[str]) -> FetchResult:
        result = FetchResult()
        for i in range(0, len(usernames), self.batch_size):
            chunk = usernames[i:i + self.batch_size]
            try:
                items, cost = self.client.run(chunk)
            except (ProviderAuthError, FreeAllowanceExhausted):
                raise
            except ProviderError as exc:
                log.warning("Apify batch failed: %s", exc)
                result.failed.extend(chunk)
                result.messages.append(f"Apify batch of {len(chunk)} failed: {exc}")
                continue
            result.actor_runs += 1
            if cost is not None:
                result.actual_cost_usd = round((result.actual_cost_usd or 0) + cost, 6)
            got = set()
            for item in items:
                if isinstance(item, dict) and item.get("username") and not item.get("error"):
                    result.profiles.append(item)
                    got.add(str(item["username"]).lower())
            result.failed.extend(u for u in chunk if u not in got)
        return result


class ApifyReels:
    """Recent reels (with play counts) for a list of usernames."""
    name = "apify"
    is_external = True

    def __init__(self, token: str, client: ApifyClient | None = None, batch_size: int = 25):
        if not token and client is None:
            raise ProviderAuthError("APIFY_TOKEN is not set.")
        self.client = client or ApifyClient(token)
        self.batch_size = batch_size

    def fetch(self, usernames: list[str], per_profile: int) -> tuple[dict[str, list[dict]], FetchResult]:
        reels: dict[str, list[dict]] = {}
        result = FetchResult()
        for i in range(0, len(usernames), self.batch_size):
            chunk = usernames[i:i + self.batch_size]
            try:
                items, cost = self.client.run(chunk, actor=REEL_ACTOR, payload={
                    "username": chunk, "resultsLimit": per_profile, "skipPinnedPosts": True})
            except (ProviderAuthError, FreeAllowanceExhausted):
                raise
            except ProviderError as exc:
                log.warning("Apify reel batch failed: %s", exc)
                result.failed.extend(chunk)
                result.messages.append(f"Apify reel batch of {len(chunk)} failed: {exc}")
                continue
            result.actor_runs += 1
            if cost is not None:
                result.actual_cost_usd = round((result.actual_cost_usd or 0) + cost, 6)
            for item in items:
                owner = str(item.get("ownerUsername") or "").lower() if isinstance(item, dict) else ""
                if owner and not item.get("error"):
                    reels.setdefault(owner, []).append(item)
        return reels, result


def hashtags_for(params: dict) -> list[str]:
    """Hashtags to search: the ones typed in, else built from the niche and sub-niche."""
    import re

    typed = [t for t in re.split(r"[\s,;#]+", params.get("hashtags") or "") if t]
    raw = typed or [params.get("sub_niche") or "", params.get("niche") or ""]
    tags = [re.sub(r"[^0-9a-z_]", "", t.lower().replace(" ", "").replace("-", "")) for t in raw]
    return list(dict.fromkeys(t for t in tags if t))[:5]


class ApifyHashtagDiscovery(DiscoveryProvider):
    """Find creators from recent reels under a hashtag. Paid per result, so it is
    gated, estimated and confirmed like profile collection."""
    name = "hashtag"
    is_external = True
    is_paid = True

    def __init__(self, token: str = "", client: ApifyClient | None = None):
        self.token, self._client = token, client

    @property
    def client(self) -> ApifyClient:
        if self._client is None:
            if not self.token:
                raise ProviderAuthError("APIFY_TOKEN is not set.")
            self._client = ApifyClient(self.token)
        return self._client

    def discover(self, params: dict, limit: int) -> DiscoveryResult:
        out = DiscoveryResult()
        tags = hashtags_for(params)
        if not tags:
            out.messages.append("Enter a niche or at least one hashtag to search.")
            return out
        per_tag = max(1, -(-limit // len(tags)))
        items, cost = self.client.run([], actor=HASHTAG_ACTOR, payload={
            "hashtags": tags, "resultsType": "reels", "resultsLimit": per_tag})
        out.actor_runs, out.actual_cost_usd = 1, cost
        found: dict[str, Handle] = {}
        for item in items:
            if not isinstance(item, dict) or item.get("error"):
                continue
            name = str(item.get("ownerUsername") or "").lower()
            if not name:
                continue
            plays = item.get("videoPlayCount") or item.get("igPlayCount")
            plays = int(plays) if isinstance(plays, (int, float)) and plays > 0 else None
            if name in found:
                if plays and (found[name].est_views is None or plays > found[name].est_views):
                    found[name].est_views = plays
                continue
            found[name] = Handle(username=name, source="hashtag", title=str(item.get("ownerFullName") or ""),
                                 snippet=str(item.get("caption") or "")[:160], est_views=plays)
        out.handles = list(found.values())[:limit]
        out.messages.append(
            f"Hashtag search (#{', #'.join(tags)}) returned {len(items)} reel(s) from {len(found)} creator(s). "
            "It shows recent reels under these hashtags, not every creator in the niche."
        )
        return out
