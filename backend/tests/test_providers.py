"""External providers are tested against fakes only. No real HTTP, no credits."""
import pytest
import requests

from app.integrations.apify_provider import ApifyClient, ApifyProfiles
from app.integrations.base import FreeAllowanceExhausted, ProviderAuthError, ProviderError
from app.integrations.mock_provider import DEMO_PROFILES, MockDiscovery, MockProfiles
from app.integrations.search_discovery import (DuckDuckGoDiscovery, ManualDiscovery, parse_ddg_html,
                                               parse_followers, parse_username_list, username_from_url)


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Plays back a scripted list of responses or exceptions."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def apify(script):
    sleeps = []
    session = FakeSession(script)
    return ApifyClient("token", session=session, sleep=sleeps.append), session, sleeps


RUN_OK = {"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1", "usageTotalUsd": 0.0131}}


# ------------------------------------------------------------------------------ Apify
SETTLED = [FakeResponse(payload=RUN_OK)] * 2  # cost re-read until it stops changing


def test_run_returns_items_and_reported_cost_and_hides_token_from_url():
    client, session, _ = apify([FakeResponse(payload=RUN_OK), FakeResponse(payload=[{"username": "a"}])] + SETTLED)
    items, cost = client.run(["a"])
    assert items == [{"username": "a"}] and cost == 0.0131
    for _, url, kwargs in session.calls:
        assert "token" not in url and kwargs["headers"]["Authorization"] == "Bearer token"


def test_run_polls_until_finished():
    running = {"data": {"id": "r1", "status": "RUNNING"}}
    client, session, _ = apify([FakeResponse(payload=running), FakeResponse(payload=running),
                                FakeResponse(payload=RUN_OK), FakeResponse(payload=[])] + SETTLED)
    assert client.run(["a"]) == ([], 0.0131)
    assert len(session.calls) == 6


def test_cost_is_read_after_apify_posts_the_event_charges():
    """Seen on a live run: $0.001 when the run finishes, $0.0088 about ten seconds later."""
    def at(cost):
        return FakeResponse(payload={"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1", "usageTotalUsd": cost}})
    client, _, sleeps = apify([at(0.001), FakeResponse(payload=[]), at(0.001), at(0.0088), at(0.0088)])
    assert client.run(["a"])[1] == 0.0088
    assert sleeps == [5, 5, 5]


def test_reel_prices_and_reel_collection_shape():
    reel_pricing = {"data": {"pricingInfos": [{"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
        "reel": {"eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.0026}, "GOLD": {"tieredEventPriceUsd": 0.0016}}},
        "actor-start": {"eventPriceUsd": 0.001}, "transcript": {"eventPriceUsd": 0.048}}}}]}}
    profile_pricing = {"data": {"pricingInfos": [{"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
        "profile": {"eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.0026}}}}}}]}}
    tag_pricing = {"data": {"pricingInfos": [{"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
        "result": {"eventTieredPricingUsd": {"FREE": {"tieredEventPriceUsd": 0.0026}}}}}}]}}
    client, _, _ = apify([FakeResponse(payload=reel_pricing), FakeResponse(payload=tag_pricing), FakeResponse(payload=profile_pricing)])
    assert client.prices() == {"usd_per_profile": 0.0026, "usd_per_reel": 0.0026, "usd_per_reel_run": 0.001,
                               "usd_per_hashtag_result": 0.0026}

    from app.integrations.apify_provider import REEL_ACTOR, ApifyReels

    class Client:
        def run(self, names, actor, payload):
            assert actor == REEL_ACTOR and payload == {"username": names, "resultsLimit": 4, "skipPinnedPosts": True}
            return [{"ownerUsername": "A", "videoPlayCount": 5}, {"ownerUsername": "a", "videoPlayCount": 7},
                    {"ownerUsername": "b", "error": "no_items"}, "junk"], 0.02

    reels, result = ApifyReels("", client=Client()).fetch(["a", "b"], 4)
    assert [r["videoPlayCount"] for r in reels["a"]] == [5, 7] and "b" not in reels
    assert result.actor_runs == 1 and result.actual_cost_usd == 0.02


def test_retries_with_exponential_backoff_on_rate_limit_and_timeouts():
    client, _, sleeps = apify([FakeResponse(429), requests.Timeout(), FakeResponse(503),
                               FakeResponse(payload={"data": {"limits": {"maxMonthlyUsageUsd": 5},
                                                              "current": {"monthlyUsageUsd": 1.25}}})])
    assert client.limits() == {"limit_usd": 5.0, "used_usd": 1.25, "remaining_usd": 3.75}
    assert sleeps == [1, 2, 4]


def test_gives_up_after_max_retries():
    client, _, _ = apify([FakeResponse(500)] * 4)
    with pytest.raises(ProviderError):
        client._request("GET", "/x")


def test_auth_and_exhausted_allowance_are_not_retried():
    client, session, _ = apify([FakeResponse(401)])
    with pytest.raises(ProviderAuthError):
        client._request("GET", "/x")
    assert len(session.calls) == 1
    client, _, _ = apify([FakeResponse(402)])
    with pytest.raises(FreeAllowanceExhausted):
        client.run(["a"])


def test_failed_run_and_invalid_json_raise():
    client, _, _ = apify([FakeResponse(payload={"data": {"id": "r1", "status": "FAILED"}})])  # no cost polling on failure
    with pytest.raises(ProviderError, match="FAILED"):
        client.run(["a"])
    client, _, _ = apify([FakeResponse(200, payload=None)])
    with pytest.raises(ProviderError, match="not valid JSON"):
        client._request("GET", "/x")


def test_run_timeout():
    running = FakeResponse(payload={"data": {"id": "r1", "status": "RUNNING"}})
    client, _, _ = apify([running, running, running])
    with pytest.raises(ProviderError, match="timed out"):
        client.run(["a"], poll_seconds=30, max_wait=60)


def test_pricing_is_read_from_the_provider_not_assumed():
    per_event = {"data": {"pricingInfos": [{"pricingModel": "PAY_PER_EVENT", "pricingPerEvent": {"actorChargeEvents": {
        "profile": {"eventTitle": "Profile", "eventPriceUsd": 0.0031}}}}]}}
    assert apify([FakeResponse(payload=per_event)])[0].current_price_per_profile() == 0.0031
    per_item = {"data": {"pricingInfos": [{"pricingModel": "PRICE_PER_DATASET_ITEM", "pricePerUnitUsd": 0.002}]}}
    assert apify([FakeResponse(payload=per_item)])[0].current_price_per_profile() == 0.002
    assert apify([FakeResponse(payload={"data": {}})])[0].current_price_per_profile() is None


def test_provider_batches_and_keeps_going_when_one_batch_fails():
    class Client:
        def __init__(self):
            self.n = 0

        def run(self, names):
            self.n += 1
            if self.n == 2:
                raise ProviderError("boom")
            return [{"username": names[0]}, {"username": "x", "error": "not_found"}, "junk"], 0.01

    result = ApifyProfiles("", client=Client(), batch_size=2).fetch(["a", "b", "c", "d", "e"])
    assert [p["username"] for p in result.profiles] == ["a", "e"]
    assert sorted(result.failed) == ["b", "c", "d"]
    assert result.actor_runs == 2 and result.actual_cost_usd == 0.02
    assert any("boom" in m for m in result.messages)


def test_apify_requires_a_token():
    with pytest.raises(ProviderAuthError):
        ApifyProfiles("")


# -------------------------------------------------------------------------- discovery
def test_username_parsing():
    assert username_from_url("https://www.instagram.com/Some.User/?hl=en") == "some.user"
    assert username_from_url("https://instagram.com/p/Cxyz123/") is None
    assert username_from_url("https://www.instagram.com/reel/abc/") is None
    assert username_from_url("https://example.com/user") is None
    assert parse_username_list("@One, two\nhttps://instagram.com/three/ bad name! ONE https://instagram.com/explore/") == [
        "one", "two", "three", "bad"]


def test_follower_snippet_parsing():
    assert parse_followers("12K Followers, 300 Following") == 12_000
    assert parse_followers("1.5M Followers") == 1_500_000
    assert parse_followers("8,421 Followers") == 8_421
    assert parse_followers("no numbers here") is None


DDG_HTML = """
<div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.instagram.com%2Ffit_anna%2F">Anna (@fit_anna)</a>
<a class="result__snippet">45K Followers - workout tips anna@gmail.com</a></div>
<div class="result"><a class="result__a" href="https://www.instagram.com/p/abc/">A post</a></div>
<div class="result"><a class="result__a" href="https://www.instagram.com/fit_anna/">Duplicate</a></div>
<div class="result"><a class="result__a" href="https://www.instagram.com/gym.bob">Bob</a><a class="result__snippet">2M Followers</a></div>
<form><input name="q" value="x"><input name="s" value="30"><input type="submit" value="Next"></form>
"""


def test_ddg_html_parsing_and_pagination_form():
    rows, nxt = parse_ddg_html(DDG_HTML)
    assert rows[0][0] == "https://www.instagram.com/fit_anna/"
    assert nxt == {"q": "x", "s": "30"}


def test_duckduckgo_discovery_dedupes_attributes_and_paginates():
    session = FakeSession([FakeResponse(text=DDG_HTML), FakeResponse(text="<html></html>")] + [FakeResponse(text="")] * 10)
    found = DuckDuckGoDiscovery(session=session, sleep=lambda s: None).discover({"niche": "fitness"}, limit=10)
    assert [(h.username, h.source, h.est_followers) for h in found.handles] == [
        ("fit_anna", "duckduckgo", 45_000), ("gym.bob", "duckduckgo", 2_000_000)]
    assert session.calls[1][2]["data"] == {"q": "x", "s": "30"}
    assert "not every account" in found.messages[-1]


def test_duckduckgo_rate_limit_is_reported_not_hidden():
    session = FakeSession([FakeResponse(202)] * 3)
    found = DuckDuckGoDiscovery(session=session, sleep=lambda s: None).discover({"niche": "fitness"}, limit=10)
    assert found.handles == [] and any("rate limit or bot check" in m for m in found.messages)


def test_manual_import_respects_limit():
    found = ManualDiscovery().discover({"usernames": "a b c d"}, limit=2)
    assert [h.username for h in found.handles] == ["a", "b"] and "first 2 of 4" in found.messages[0]


# ---------------------------------------------------------------------------- demo data
def test_demo_data_is_clearly_fictional():
    assert len(DEMO_PROFILES) == 72
    for username, raw in DEMO_PROFILES.items():
        assert username.startswith("demo_") and raw["isDemo"] is True and "(Demo)" in raw["fullName"]
        assert "@" not in raw["biography"] or ".example" in raw["biography"]


def test_demo_discovery_filters_and_labels():
    found = MockDiscovery().discover({"niche": "Fitness", "country": "india"}, limit=50)
    assert len(found.handles) == 2 and found.messages[0].startswith("DEMO DATA")
    assert "No DEMO DATA matches" in " ".join(MockDiscovery().discover({"niche": "astrology"}, 50).messages)


def test_demo_provider_never_invents_data_for_real_usernames():
    result = MockProfiles().fetch(["demo_fitness_aarav", "a_real_person"])
    assert len(result.profiles) == 1 and result.failed == ["a_real_person"]
    assert "nothing was invented" in result.messages[0]


# ------------------------------------------------------------------ hashtag discovery
def test_hashtags_come_from_typed_tags_or_the_niche():
    from app.integrations.apify_provider import hashtags_for

    assert hashtags_for({"niche": "Home Workout", "sub_niche": "weight-loss"}) == ["weightloss", "homeworkout"]
    assert hashtags_for({"niche": "fitness", "hashtags": "#HomeWorkout, #yoga  yoga"}) == ["homeworkout", "yoga"]
    assert hashtags_for({"niche": "  ", "hashtags": ""}) == []
    assert len(hashtags_for({"hashtags": "a b c d e f g"})) == 5


def test_hashtag_discovery_dedupes_owners_keeps_best_plays_and_reports_cost():
    from app.integrations.apify_provider import HASHTAG_ACTOR, ApifyHashtagDiscovery

    class Client:
        def run(self, names, actor, payload):
            assert actor == HASHTAG_ACTOR
            assert payload == {"hashtags": ["homeworkout", "yoga"], "resultsType": "reels", "resultsLimit": 5}
            return [{"ownerUsername": "Fit.Anna", "ownerFullName": "Anna", "videoPlayCount": 40_000, "caption": "plank"},
                    {"ownerUsername": "fit.anna", "videoPlayCount": 90_000},
                    {"ownerUsername": "gymbob", "videoPlayCount": None},
                    {"ownerUsername": "", "videoPlayCount": 5}, {"error": "blocked"}, "junk"], 0.0156

    found = ApifyHashtagDiscovery(client=Client()).discover({"hashtags": "homeworkout yoga"}, limit=10)
    assert [(h.username, h.source, h.est_views) for h in found.handles] == [("fit.anna", "hashtag", 90_000), ("gymbob", "hashtag", None)]
    assert found.actual_cost_usd == 0.0156 and found.actor_runs == 1
    assert "not every creator" in found.messages[-1]


def test_hashtag_discovery_needs_a_niche_or_tag_and_a_token():
    from app.integrations.apify_provider import ApifyHashtagDiscovery

    empty = ApifyHashtagDiscovery("").discover({"niche": ""}, 10)
    assert empty.handles == [] and "Enter a niche" in empty.messages[0]
    with pytest.raises(ProviderAuthError):
        ApifyHashtagDiscovery("").discover({"niche": "fitness"}, 10)
