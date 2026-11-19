import io
from datetime import timedelta

import pandas as pd
import pytest

from app import integrations
from app.core import config as config_module
from app.integrations.base import FetchResult, FreeAllowanceExhausted, ProviderError
from app.models import Creator, SearchRun, utcnow
from app.services import costs, pipeline
from app.services.exports import COLUMNS
from app.services.settings_store import get_settings

from .conftest import PASSWORD, fake_search, login_as


# ------------------------------------------------------------------------------- auth
def test_setup_only_once_and_login(anon, client):
    assert anon.get("/api/auth/status").json() == {"needs_setup": False}
    again = anon.post("/api/auth/setup", json={"email": "x@test.local", "name": "X", "password": PASSWORD})
    assert again.status_code == 409
    assert anon.post("/api/auth/login", json={"email": "admin@test.local", "password": "wrong-password"}).status_code == 401
    assert anon.post("/api/auth/login", json={"email": "ADMIN@test.local", "password": PASSWORD}).status_code == 200


def test_everything_requires_sign_in(anon):
    for path in ("/api/creators", "/api/dashboard", "/api/campaigns", "/api/settings", "/api/costs",
                 "/api/export", "/api/clients", "/api/outreach", "/api/partnerships", "/api/users"):
        assert anon.get(path).status_code == 401, path
    anon.headers["Authorization"] = "Bearer not-a-real-token"
    assert anon.get("/api/creators").status_code == 401


def test_login_lockout_after_repeated_failures(anon, client):
    for _ in range(5):
        anon.post("/api/auth/login", json={"email": "admin@test.local", "password": "nope-nope"})
    assert anon.post("/api/auth/login", json={"email": "admin@test.local", "password": PASSWORD}).status_code == 429


def test_weak_password_rejected(anon):
    assert anon.post("/api/auth/setup", json={"email": "a@b.co", "name": "A", "password": "short"}).status_code == 422


# -------------------------------------------------------------------- search pipeline
def test_fake_search_end_to_end(client):
    run = fake_search(client, "fitness")
    assert run["discovered"] == 6 and run["collected"] == 6
    assert run["qualified"] + run["needs_review"] + run["rejected"] == 6
    assert run["qualified"] == 2 and run["needs_review"] == 2 and run["rejected"] == 2
    assert run["actual_cost_usd"] is None and run["actor_runs"] == 2  # profiles, then reels
    by_name = {r["username"]: r for r in run["results"]}
    assert by_name["fake_fitness_oliver"]["selling_status"] == "SELLING"
    assert by_name["fake_fitness_oliver"]["verdict"] == "rejected"
    assert by_name["fake_fitness_priya"]["selling_status"] == "CHECK"
    assert by_name["fake_fitness_priya"]["verdict"] == "needs_review"
    assert by_name["fake_fitness_liam"]["has_email"] is False
    assert by_name["fake_fitness_liam"]["verdict"] == "needs_review"  # no email: review for DM outreach
    assert by_name["fake_fitness_aarav"]["verdict"] == "qualified"
    assert by_name["fake_fitness_emily"]["email"].endswith(".example")
    # The pipeline stage follows the verdict automatically for new creators.
    assert by_name["fake_fitness_aarav"]["crm_status"] == "Qualified"
    assert by_name["fake_fitness_priya"]["crm_status"] == "Needs Review"
    assert by_name["fake_fitness_oliver"]["crm_status"] == "Not Qualified"


def test_repeat_search_uses_cache_and_never_duplicates(client, db):
    fake_search(client, "fitness")
    second = fake_search(client, "fitness")
    assert second["cached"] == 6 and second["requested"] == 0 and second["collected"] == 0
    assert all(r["from_cache"] for r in second["results"])
    assert db.query(Creator).count() == 6
    assert client.get("/api/creators").json()["total"] == 6


def test_cache_expires_and_refresh_forces_collection(client, db):
    fake_search(client, "fitness")
    for c in db.query(Creator).all():
        c.last_collected_at = utcnow() - timedelta(days=15)
    db.commit()
    assert fake_search(client, "fitness")["cached"] == 0
    assert fake_search(client, "fitness")["cached"] == 6
    forced = fake_search(client, "fitness", refresh=True)
    assert forced["cached"] == 0 and forced["collected"] == 6
    detail = client.get(f"/api/creators/{forced['results'][0]['id']}").json()
    assert len(detail["history"]) == 3  # every collection is kept for trend analysis


def test_search_filters_are_applied_per_search(client):
    strict = fake_search(client, "fitness", filters={"min_followers": 95_000})
    assert strict["qualified"] == 0
    relaxed = fake_search(client, "fitness", filters={"require_email": False, "exclude_selling": False,
                                                      "max_followers": 5_000_000, "min_views": 0, "max_views": 10**9})
    assert relaxed["qualified"] >= 5


def test_invalid_filter_ranges_are_rejected(client):
    res = client.post("/api/discovery/run", json={"niche": "fitness", "filters": {"min_followers": 9, "max_followers": 1}})
    assert res.status_code == 422


def test_manual_import_of_real_usernames_invents_nothing(client):
    res = client.post("/api/discovery/run", json={"discovery_source": "manual", "profile_provider": "none",
                                                  "usernames": "@real_person, https://instagram.com/another.one/"})
    run = res.json()["run"]
    assert run["discovered"] == 2 and run["collected"] == 0 and run["needs_review"] == 2
    row = run["results"][0]
    assert row["collected"] is False
    assert row["followers"] is None and row["lead_score"] is None and row["selling_status"] == "UNKNOWN"


def test_max_profiles_limit_is_enforced(client):
    client.put("/api/settings", json={"max_profiles_per_search": 3})
    assert fake_search(client, "fitness", max_profiles=500)["discovered"] == 3


# --------------------------------------------------------------- cost protection (Apify)
def test_there_is_no_demo_mode_any_more(client):
    for source in ("demo",):
        assert client.post("/api/discovery/run", json={"discovery_source": source, "niche": "fitness"}).status_code == 422
    assert client.post("/api/discovery/run", json={"profile_provider": "demo", "niche": "fitness"}).status_code == 422
    assert "provider_mode" not in client.get("/api/settings").json()
    assert "demo_niches" not in client.get("/api/meta").json()


def test_external_call_requires_confirmation_and_makes_no_call(client, fake_apify, monkeypatch):
    res = client.post("/api/discovery/run", json={"discovery_source": "manual", "profile_provider": "apify",
                                                  "usernames": "a b c"})
    body = res.json()
    assert body["needs_confirmation"] is True and body["allowed"] is True
    assert body["max_profiles"] == 3 and "Apify profile and reel collection" in body["external_calls"]
    assert fake_apify["profiles"].calls == []  # nothing collected before confirmation
    monkeypatch.setattr(config_module.config, "apify_token", "")
    body = client.post("/api/discovery/run", json={"discovery_source": "manual", "profile_provider": "apify",
                                                   "usernames": "a b c"}).json()
    assert body["allowed"] is False and "No Apify token is saved" in body["reasons"][0]


class FakeApify:
    """Shaped like the real profile Actor: posts carry likes but NO view counts."""
    name, is_external = "apify", True

    def __init__(self, cost=0.008, error=None, small=()):
        self.cost, self.error, self.small, self.calls = cost, error, small, []

    def fetch(self, usernames):
        self.calls.append(usernames)
        if self.error:
            raise self.error
        return FetchResult(actor_runs=1, actual_cost_usd=self.cost, profiles=[
            {"username": u, "followersCount": 900 if u in self.small else 30_000, "biography": f"gym workouts {u}@mail.com",
             "latestPosts": [{"type": "Video", "likesCount": 900, "commentsCount": 30}, {"type": "Image", "likesCount": 500}]}
            for u in usernames])


class FakeReels:
    """Shaped like the real reel Actor: one item per reel with videoPlayCount."""

    def __init__(self, cost=0.021, error=None):
        self.cost, self.error, self.calls = cost, error, []

    def fetch(self, usernames, per_profile):
        self.calls.append((usernames, per_profile))
        if self.error:
            raise self.error
        reels = {u: [{"ownerUsername": u, "type": "Video", "productType": "clips", "videoPlayCount": v}
                     for v in (70_000, 90_000, 110_000)][:per_profile] for u in usernames}
        return reels, FetchResult(actor_runs=1, actual_cost_usd=self.cost)


class FakeHashtags:
    """Shaped like the hashtag Actor's result after our provider has grouped it by creator."""
    name, is_external, is_paid = "hashtag", True, True

    def __init__(self, error=None):
        self.error, self.calls = error, []

    def discover(self, params, limit):
        from app.integrations.base import DiscoveryResult, Handle

        self.calls.append((params.get("niche"), params.get("hashtags"), limit))
        if self.error:
            raise self.error
        handles = [Handle("alpha", "hashtag", est_views=80_000), Handle("beta", "hashtag", est_views=120_000),
                   Handle("tiny", "hashtag", est_views=900), Handle("viral", "hashtag", est_views=9_000_000)]
        return DiscoveryResult(handles=handles[:limit], messages=["Hashtag search (#fitness) returned 4 reel(s) from 4 creator(s)."],
                               actor_runs=1, actual_cost_usd=0.012)


@pytest.fixture
def live(client, monkeypatch):
    """Live mode with fake Apify: allowance $5, $1 used, $0.004/profile, $0.002/reel, $0.001/reel run."""
    state = {"limits": {"limit_usd": 5.0, "used_usd": 1.0, "remaining_usd": 4.0},
             "prices": {"usd_per_profile": 0.004, "usd_per_reel": 0.002, "usd_per_reel_run": 0.001,
                        "usd_per_hashtag_result": 0.003},
             "provider": FakeApify(), "reels": FakeReels(), "discovery": FakeHashtags()}
    monkeypatch.setattr(pipeline.ApifyClient, "limits", lambda self: state["limits"])
    monkeypatch.setattr(pipeline.ApifyClient, "prices", lambda self: state["prices"])
    monkeypatch.setattr(integrations, "get_profile_provider", lambda name: state["provider"])
    monkeypatch.setattr(integrations, "get_reel_provider", lambda name: state["reels"])
    real_get = integrations.get_discovery
    monkeypatch.setattr(integrations, "get_discovery", lambda name: state["discovery"] if name == "hashtag" else real_get(name))
    return state


def apify_search(client, **extra):
    return client.post("/api/discovery/run", json={"discovery_source": "manual", "profile_provider": "apify",
                                                   "usernames": "alpha beta", "niche": "fitness", **extra})


def test_confirmation_shows_upper_bound_estimate_from_provider_pricing(client, live):
    body = apify_search(client).json()
    assert body["needs_confirmation"] and body["allowed"]
    est = body["estimate"]
    # 2 profiles x $0.004, plus at most 2 creators x 5 reels x $0.002 and one reel run at $0.001
    assert est["profiles_usd"] == 0.008 and est["reels_usd_max"] == 0.021 and est["estimated_usd"] == 0.029
    assert est["estimated_inr"] == 2.61 and est["is_estimate"] is True and est["is_upper_bound"] is True
    assert body["limits"]["remaining_usd"] == 4.0
    assert live["provider"].calls == [] and live["reels"].calls == []  # nothing fetched before confirmation


def test_confirmed_live_search_collects_profiles_then_reels(client, live, db):
    run = apify_search(client, confirmed=True).json()["run"]
    assert run["collected"] == 2 and run["actor_runs"] == 2
    assert run["est_cost_usd"] == 0.029 and run["actual_cost_usd"] == 0.029  # 0.008 profiles + 0.021 reels
    assert live["reels"].calls == [(["alpha", "beta"], 5)]
    row = run["results"][0]
    assert row["email"] == "alpha@mail.com"
    assert row["median_reel_views"] == 90_000 and row["reels_analyzed"] == 3 and row["verdict"] == "qualified"
    pricing = get_settings(db)["apify_pricing"]
    assert pricing["usd_per_profile"] == 0.004 and pricing["usd_per_reel"] == 0.002 and pricing["source"] == "Apify Actor pricing API"
    report = client.get("/api/costs").json()
    assert report["month"]["actual_cost_usd"] == 0.029 and report["month"]["actual_cost_inr"] == 2.61
    assert report["month"]["cost_per_profile_usd"] == 0.0145 and report["month"]["cost_per_qualified_usd"] == 0.0145
    assert any(a["action"] == "search.external" for a in client.get("/api/audit").json())


def test_reels_are_only_bought_for_creators_that_pass_the_cheap_checks(client, live):
    live["provider"] = FakeApify(small=("beta",))  # beta has 900 followers: rejected on the profile alone
    run = apify_search(client, confirmed=True).json()["run"]
    assert live["reels"].calls == [(["alpha"], 5)]
    by = {r["username"]: r for r in run["results"]}
    assert by["alpha"]["verdict"] == "qualified" and by["beta"]["verdict"] == "rejected"
    assert by["beta"]["median_reel_views"] is None
    assert run["est_cost_usd"] == 0.019  # 2 profiles + reels for one creator only
    assert any("Reel views were collected for 1 of 2" in m for m in run["messages"])


def test_no_email_creators_get_reels_for_review_unless_the_strict_rule_is_on(client, live):
    class NoEmail(FakeApify):
        def fetch(self, usernames):
            result = super().fetch(usernames)
            for p in result.profiles:
                if p["username"] == "beta":
                    p["biography"] = "gym workouts, DM me"
            return result

    live["provider"] = NoEmail()
    run = apify_search(client, confirmed=True).json()["run"]
    by = {r["username"]: r for r in run["results"]}
    assert live["reels"].calls == [(["alpha", "beta"], 5)]  # beta's views are needed to judge it
    assert by["beta"]["verdict"] == "needs_review" and by["beta"]["median_reel_views"] == 90_000
    assert "Instagram message" in by["beta"]["verdict_reasons"][0]

    live["provider"], live["reels"] = NoEmail(), FakeReels()
    strict = apify_search(client, confirmed=True, refresh=True, filters={"no_email_to_review": False}).json()["run"]
    by = {r["username"]: r for r in strict["results"]}
    assert live["reels"].calls == [(["alpha"], 5)]  # strict: no reels bought for a creator already rejected
    assert by["beta"]["verdict"] == "rejected"


def test_profile_without_reel_stage_needs_review_not_rejected(client, live):
    live["reels"] = FakeReels(error=ProviderError("reel actor down"))
    run = apify_search(client, confirmed=True).json()["run"]
    assert run["needs_review"] == 2 and run["actual_cost_usd"] == 0.008
    assert any("Reel collection failed" in m for m in run["messages"])
    live["reels"] = FakeReels()
    again = apify_search(client, confirmed=True).json()["run"]  # profiles cached, reels still missing: only reels are bought
    assert again["cached"] == 2 and again["requested"] == 0 and again["qualified"] == 2
    assert len(live["provider"].calls) == 1 and again["actual_cost_usd"] == 0.021


def test_cached_profiles_and_reels_are_not_paid_for_twice(client, live):
    apify_search(client, confirmed=True)
    second = apify_search(client, confirmed=True).json()["run"]
    assert second["cached"] == 2 and second["requested"] == 0 and second["qualified"] == 2
    assert second["actual_cost_usd"] is None
    assert len(live["provider"].calls) == 1 and len(live["reels"].calls) == 1


def test_insufficient_free_allowance_skips_collection(client, live):
    live["limits"] = {"limit_usd": 5.0, "used_usd": 4.999, "remaining_usd": 0.001}
    assert apify_search(client).json()["allowed"] is False
    run = apify_search(client, confirmed=True).json()["run"]
    assert run["collected"] == 0 and live["provider"].calls == [] and live["reels"].calls == []
    assert any("No paid call was made" in m for m in run["messages"])


def test_exhausted_allowance_stops_without_payment(client, live):
    live["provider"] = FakeApify(error=FreeAllowanceExhausted("Apify's free allowance for this month is used up."))
    run = apify_search(client, confirmed=True).json()["run"]
    assert run["collected"] == 0 and any("No payment was made" in m for m in run["messages"])


def test_allowance_running_out_at_the_reel_stage_also_stops(client, live):
    live["reels"] = FakeReels(error=FreeAllowanceExhausted("Apify's free allowance for this month is used up."))
    run = apify_search(client, confirmed=True).json()["run"]
    assert run["collected"] == 2 and run["needs_review"] == 2
    assert any("No payment was made" in m for m in run["messages"])


def hashtag_search(client, **extra):
    return client.post("/api/discovery/run", json={"discovery_source": "hashtag", "profile_provider": "apify",
                                                   "niche": "fitness", "max_profiles": 4, **extra})


def test_hashtag_search_is_estimated_and_confirmed_before_any_spend(client, live):
    body = hashtag_search(client).json()
    assert body["needs_confirmation"] and body["allowed"]
    assert body["external_calls"] == ["Apify hashtag search", "Apify profile and reel collection"]
    est = body["estimate"]
    # 4 search results x $0.003, 4 profiles x $0.004, reels for at most 4 creators (4 x 5 x $0.002 + $0.001)
    assert est["discovery_usd"] == 0.012 and est["profiles_usd"] == 0.016 and est["reels_usd_max"] == 0.041
    assert est["estimated_usd"] == 0.069
    assert live["discovery"].calls == [] and live["provider"].calls == []


def test_hashtag_search_end_to_end_skips_out_of_range_views_before_paying_for_profiles(client, live):
    run = hashtag_search(client, confirmed=True).json()["run"]
    assert live["discovery"].calls == [("fitness", "", 4)]
    assert live["provider"].calls == [["alpha", "beta"]]  # tiny (900 plays) and viral (9M) were never bought
    assert run["discovered"] == 4 and run["collected"] == 2 and run["qualified"] == 2 and run["actor_runs"] == 3
    assert any("2 creator(s) skipped before profile collection" in m for m in run["messages"])
    assert run["actual_cost_usd"] == 0.041  # search 0.012 + profiles 0.008 + reels 0.021
    assert run["est_cost_usd"] == 0.041     # search 0.012 + 2 profiles 0.008 + reels for 2 (0.021)
    assert {r["source"] for r in run["results"]} == {"hashtag"}


def test_hashtag_search_is_refused_without_a_token_or_when_allowance_is_short(client, live, monkeypatch):
    live["limits"] = {"limit_usd": 5.0, "used_usd": 4.995, "remaining_usd": 0.005}
    res = hashtag_search(client, confirmed=True)
    assert res.status_code == 400 and "The hashtag search was not run" in res.json()["detail"]
    assert live["discovery"].calls == []
    monkeypatch.setattr(config_module.config, "apify_token", "")
    res = hashtag_search(client, confirmed=True)
    assert res.status_code == 400 and "No Apify token is saved" in res.json()["detail"] and live["discovery"].calls == []


def test_hashtag_search_allowance_exhausted_stops_without_payment(client, live):
    live["discovery"] = FakeHashtags(error=FreeAllowanceExhausted("Apify's free allowance for this month is used up."))
    res = hashtag_search(client, confirmed=True)
    assert res.status_code == 400 and "No payment was made" in res.json()["detail"]


def test_zero_budget_blocks_spend_beyond_free_allowance(client, live, db):
    db.add(SearchRun(profile_provider="apify", actual_cost_usd=5.2, collected=100, qualified=10))
    db.commit()
    live["limits"] = {"limit_usd": 50.0, "used_usd": 5.2, "remaining_usd": 44.8}  # e.g. a paid plan later
    body = apify_search(client).json()
    assert body["allowed"] is True  # still inside this account's allowance
    live["limits"] = {"limit_usd": 5.0, "used_usd": 4.0, "remaining_usd": 1.0}
    body = apify_search(client).json()
    assert body["allowed"] is False and body["budget"]["level"] == "blocked"
    assert "above the monthly budget of ₹0" in " ".join(body["reasons"])


def test_budget_levels_and_cost_math(db):
    settings = get_settings(db)
    settings["monthly_budget_inr"] = 500
    db.add(SearchRun(profile_provider="apify", est_cost_usd=2.0, actual_cost_usd=None, collected=400, qualified=20))
    db.add(SearchRun(profile_provider="apify", est_cost_usd=1.0, actual_cost_usd=1.5, collected=100, qualified=5))
    db.commit()
    usage = costs.usage_summary(db)
    assert usage["estimated_cost_usd"] == 3.0 and usage["actual_cost_usd"] == 1.5
    assert usage["best_known_cost_usd"] == 3.5  # actual where reported, estimate otherwise
    assert usage["cost_per_profile_usd"] == 0.007 and usage["cost_per_qualified_usd"] == 0.14
    assert usage["searches"] == 2 and usage["live_qualified"] == 25
    assert costs.budget_state(db, settings, 0)["level"] == "ok"            # ₹315 of ₹500
    assert costs.budget_state(db, settings, 1.0)["level"] == "warning"     # ₹405 = 81%
    assert costs.budget_state(db, settings, 3.0)["level"] == "blocked"     # ₹585
    assert costs.budget_state(db, settings, 3.0, free_allowance_usd=5.0)["level"] == "ok"
    assert costs.estimate_fetch(10, settings)["estimated_usd"] is None  # unknown price is not guessed
    assert costs.estimate_fetch(30, settings)["large_search"] is True
    settings["apify_pricing"] = {"usd_per_profile": 0.0026, "usd_per_reel": 0.0026, "usd_per_reel_run": 0.001}
    full = costs.estimate_fetch(100, settings)  # 100 profiles, all to the reel stage, 4 reel runs
    assert full["profiles_usd"] == 0.26 and full["reels_usd_max"] == 1.304 and full["estimated_usd"] == 1.564
    assert costs.estimate_fetch(100, settings, 20)["estimated_usd"] == 0.521  # only 20 reach the reel stage
    assert costs.estimate_fetch(0, settings, 0)["estimated_usd"] == 0


# -------------------------------------------------------------------------- CRM workflow
def first_creator(client, username="fake_fitness_aarav"):
    return client.get("/api/creators", params={"search": username}).json()["items"][0]


def test_crm_status_notes_tags_owner_and_history(client):
    fake_search(client)
    cid = first_creator(client)["id"]
    me = client.get("/api/auth/me").json()
    res = client.patch(f"/api/creators/{cid}", json={"crm_status": "Interested", "tags": ["hot", "hot", " india "],
                                                     "owner_id": me["id"], "follow_up_date": "2030-01-15"})
    body = res.json()
    assert body["crm_status"] == "Interested" and body["tags"] == ["hot", "india"] and body["follow_up_date"] == "2030-01-15"
    client.post(f"/api/creators/{cid}/notes", json={"text": "Called, sounds keen"})
    actions = [a["action"] for a in client.get(f"/api/creators/{cid}").json()["activities"]]
    assert {"status", "tags", "owner", "follow_up", "note", "created"} <= set(actions)
    assert client.patch(f"/api/creators/{cid}", json={"crm_status": "Nonsense"}).status_code == 422
    fake_search(client, refresh=True)  # re-analysis must not overwrite a manual pipeline stage
    assert client.get(f"/api/creators/{cid}").json()["crm_status"] == "Interested"


def test_list_filters_sorting_and_pagination(client):
    fake_search(client, "fitness")
    fake_search(client, "food")
    get = lambda **p: client.get("/api/creators", params=p).json()
    assert get()["total"] == 12
    assert get(niche="food")["total"] == 6
    assert get(selling_status="SELLING")["total"] == 2
    assert get(has_email=False)["total"] == get(verdict="needs_review", has_email=False)["total"] == 2
    assert get(country="India", niche="fitness")["total"] == 2
    scores = [c["lead_score"] for c in get(sort="lead_score", order="desc")["items"] if c["lead_score"] is not None]
    assert scores == sorted(scores, reverse=True)
    page = get(page=2, page_size=5)
    assert len(page["items"]) == 5 and page["page"] == 2


def test_selling_override_is_recorded_and_changes_verdict(client):
    fake_search(client)
    c = first_creator(client, "fake_fitness_priya")
    assert c["verdict"] == "needs_review"
    body = client.post(f"/api/creators/{c['id']}/selling-override", json={"status": "NOT_SELLING", "note": "Checked link page"}).json()
    assert body["selling_status"] == "NOT_SELLING" and body["selling_detected"] == "CHECK"
    assert body["selling_override"]["by"] == "Admin" and body["selling_override"]["at"]
    assert body["verdict"] == "qualified"
    cleared = client.post(f"/api/creators/{c['id']}/selling-override", json={"status": None}).json()
    assert cleared["selling_status"] == "CHECK" and cleared["verdict"] == "needs_review"


def test_contact_verification_and_deletion(client, monkeypatch):
    fake_search(client)
    c = client.get(f"/api/creators/{first_creator(client)['id']}").json()
    contact = c["contacts"][0]
    assert contact["validation_status"] == "syntax_validated" and contact["source"] == "biography"
    monkeypatch.setattr("app.services.analysis.check_mx", lambda domain: True)
    verified = client.post(f"/api/creators/{c['id']}/contacts/{contact['id']}/verify").json()
    assert verified["contacts"][0]["validation_status"] == "mx_checked"
    assert verified["score_breakdown"]["contact"]["points"] == 10
    gone = client.delete(f"/api/creators/{c['id']}/contacts/{contact['id']}").json()
    assert gone["contacts"] == [] and gone["verdict"] == "needs_review"


def test_creator_can_be_deleted_completely(client, db):
    run = fake_search(client)
    cid = run["results"][0]["id"]
    assert client.delete(f"/api/creators/{cid}").json() == {"deleted": True}
    assert client.get(f"/api/creators/{cid}").status_code == 404
    assert db.query(Creator).count() == 5


def test_similar_creators_come_with_reasons(client):
    fake_search(client, "fitness")
    fake_search(client, "travel")
    body = client.get(f"/api/creators/{first_creator(client)['id']}/similar").json()
    assert body["similar"] and all(s["niche"] == "fitness" for s in body["similar"][:3])
    assert all(s["similar_reasons"] for s in body["similar"])


# ------------------------------------------------------- clients, campaigns, isolation
def make_client_setup(client):
    """Two clients, one campaign each, one client-portal user each, plus a staff user."""
    out = {}
    run = fake_search(client)
    ids = [r["id"] for r in run["results"]]
    for key in ("acme", "zen"):
        cl = client.post("/api/clients", json={"name": f"{key} ltd"}).json()
        camp = client.post("/api/campaigns", json={"name": f"{key} launch", "client_id": cl["id"], "niche": "fitness"}).json()
        client.post("/api/users", json={"email": f"{key}@test.local", "name": key, "password": PASSWORD,
                                        "role": "client", "client_id": cl["id"]})
        out[key] = {"client": cl, "campaign": camp}
    client.post("/api/users", json={"email": "staff@test.local", "name": "Staff", "password": PASSWORD, "role": "staff"})
    client.post(f"/api/campaigns/{out['acme']['campaign']['id']}/creators", json={"creator_ids": ids[:3], "shortlisted": True})
    client.post(f"/api/campaigns/{out['acme']['campaign']['id']}/creators", json={"creator_ids": ids[3:4]})
    client.post(f"/api/campaigns/{out['zen']['campaign']['id']}/creators", json={"creator_ids": ids[4:], "shortlisted": True})
    return out, ids


def test_creator_is_added_to_a_campaign_only_once(client):
    setup, ids = make_client_setup(client)
    again = client.post(f"/api/campaigns/{setup['acme']['campaign']['id']}/creators", json={"creator_ids": ids[:2]}).json()
    assert again == {"added": 0, "already_in_campaign": 2}


def test_client_sees_only_own_shortlisted_leads(client):
    setup, _ = make_client_setup(client)
    acme, zen_campaign = login_as("acme@test.local"), setup["zen"]["campaign"]["id"]
    campaigns = acme.get("/api/campaigns").json()
    assert [c["name"] for c in campaigns] == ["acme launch"] and campaigns[0]["creators"] == 3
    detail = acme.get(f"/api/campaigns/{setup['acme']['campaign']['id']}").json()
    assert len(detail["links"]) == 3  # the 4th creator is not shortlisted, so it stays internal
    assert "crm_status" not in detail["links"][0]["creator"] and "tags" not in detail["links"][0]["creator"]
    # Another client's campaign does not exist as far as this user can tell.
    assert acme.get(f"/api/campaigns/{zen_campaign}").status_code == 404
    assert acme.get("/api/export", params={"scope": "campaign", "campaign_id": zen_campaign}).status_code == 404
    zen_link = client.get(f"/api/campaigns/{zen_campaign}").json()["links"][0]["id"]
    assert acme.post(f"/api/campaigns/{zen_campaign}/creators/{zen_link}/decision", json={"approval": "approved"}).status_code == 404


def test_client_cannot_reach_internal_endpoints(client):
    setup, ids = make_client_setup(client)
    acme = login_as("acme@test.local")
    cid = setup["acme"]["campaign"]["id"]
    blocked = [
        ("get", "/api/creators"), ("get", f"/api/creators/{ids[0]}"), ("get", "/api/dashboard"), ("get", "/api/clients"),
        ("get", "/api/settings"), ("get", "/api/costs"), ("get", "/api/outreach"), ("get", "/api/partnerships"),
        ("get", "/api/users"), ("get", "/api/audit"), ("get", "/api/discovery/runs"), ("get", "/api/meta"),
        ("get", "/api/export?scope=all"), ("post", "/api/discovery/run"), ("post", "/api/campaigns"),
        ("post", f"/api/campaigns/{cid}/creators"), ("delete", f"/api/campaigns/{cid}"),
        ("delete", f"/api/creators/{ids[0]}"), ("put", "/api/settings"),
    ]
    for method, path in blocked:
        res = getattr(acme, method)(path, **({"json": {}} if method in ("post", "put") else {}))
        assert res.status_code == 403, (method, path, res.status_code)


def test_client_can_approve_own_leads_and_export_them(client):
    setup, _ = make_client_setup(client)
    acme, cid = login_as("acme@test.local"), setup["acme"]["campaign"]["id"]
    links = client.get(f"/api/campaigns/{cid}").json()["links"]
    shortlisted = next(l for l in links if l["shortlisted"])
    hidden = next(l for l in links if not l["shortlisted"])
    ok = acme.post(f"/api/campaigns/{cid}/creators/{shortlisted['id']}/decision", json={"approval": "approved", "note": "Great fit"})
    assert ok.status_code == 200 and ok.json()["approval"] == "approved"
    assert acme.post(f"/api/campaigns/{cid}/creators/{hidden['id']}/decision", json={"approval": "approved"}).status_code == 404
    client.post(f"/api/creators/{shortlisted['creator']['id']}/notes", json={"text": "INTERNAL margin note"})
    res = acme.get("/api/export", params={"scope": "campaign", "campaign_id": cid, "fmt": "csv"})
    df = pd.read_csv(io.BytesIO(res.content))
    assert len(df) == 3 and df["Campaign"].unique().tolist() == ["acme launch"]
    assert "INTERNAL" not in res.text
    assert client.get(f"/api/campaigns/{cid}").json()["approved"] == 1


def test_staff_can_work_but_not_administer(client):
    make_client_setup(client)
    staff = login_as("staff@test.local")
    assert staff.get("/api/creators").status_code == 200 and staff.get("/api/settings").status_code == 200
    assert staff.put("/api/settings", json={"sender_name": "x"}).status_code == 403
    assert staff.get("/api/users").status_code == 403 and staff.get("/api/audit").status_code == 403


def test_deactivated_user_loses_access_and_client_user_needs_a_client(client):
    make_client_setup(client)
    staff = login_as("staff@test.local")
    staff_id = next(u["id"] for u in client.get("/api/users").json() if u["email"] == "staff@test.local")
    client.patch(f"/api/users/{staff_id}", json={"is_active": False})
    assert staff.get("/api/creators").status_code == 401
    bad = client.post("/api/users", json={"email": "c@test.local", "name": "C", "password": PASSWORD, "role": "client"})
    assert bad.status_code == 422
    me = client.get("/api/auth/me").json()
    assert client.patch(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 422


def test_own_campaign_and_client_delete_rules(client):
    own = client.post("/api/campaigns", json={"name": "Our ebook launch"}).json()
    assert own["type"] == "own" and own["client_name"] is None
    setup, _ = make_client_setup(client)
    assert client.delete(f"/api/clients/{setup['acme']['client']['id']}").status_code == 409
    assert client.post("/api/clients", json={"name": "acme ltd"}).status_code == 409


# ----------------------------------------------------------------- outreach, partnerships
def test_outreach_draft_is_personalised_and_human_sent(client):
    fake_search(client)
    client.put("/api/settings", json={"sender_name": "Amit"})
    c = first_creator(client)
    draft = client.post("/api/outreach/draft", json={"creator_id": c["id"]}).json()
    assert draft["status"] == "draft" and draft["contacted_at"] is None
    assert draft["body"].startswith("Hi Aarav,") and "about fitness" in draft["body"] and "Best,\nAmit" in draft["body"]
    assert draft["subject"] == "Collaboration idea for fake_fitness_aarav"
    sent = client.patch(f"/api/outreach/{draft['id']}", json={"status": "contacted", "follow_up_date": "2030-02-01"}).json()
    assert sent["contacted_at"] and first_creator(client)["crm_status"] == "Contacted"
    client.patch(f"/api/outreach/{draft['id']}", json={"status": "replied", "notes": "Wants details"})
    assert first_creator(client)["crm_status"] == "Replied"
    assert client.patch(f"/api/outreach/{draft['id']}", json={"status": "sent-by-robot"}).status_code == 422
    assert client.get("/api/outreach", params={"status": "replied"}).json()[0]["notes"] == "Wants details"


def test_templates_are_editable_and_bad_placeholders_do_not_crash(client):
    fake_search(client)
    t = client.post("/api/outreach/templates", json={"name": "Odd", "subject": "Hi {username}", "body": "Hey {first_name} {unknown} {"}).json()
    draft = client.post("/api/outreach/draft", json={"creator_id": first_creator(client)["id"], "template_id": t["id"]}).json()
    assert draft["subject"] == "Hi fake_fitness_aarav" and "{" in draft["body"]
    client.put(f"/api/outreach/templates/{t['id']}", json={"name": "Odd", "subject": "", "body": "Hello {first_name}, re {product}"})
    draft = client.post("/api/outreach/draft", json={"creator_id": first_creator(client)["id"], "template_id": t["id"], "product": "Fit Guide"}).json()
    assert draft["body"] == "Hello Aarav, re Fit Guide"


def test_partnership_revenue_and_commission_math(client):
    fake_search(client)
    c = first_creator(client)
    product = client.post("/api/products", json={"name": "Fitness PDF", "price": 499}).json()
    p = client.post("/api/partnerships", json={"creator_id": c["id"], "product_id": product["id"], "commission_pct": 30,
                                               "fixed_payment": 1000, "revenue": 20000, "amount_paid": 2500,
                                               "promo_code": "AARAV10", "conversions": 40}).json()
    assert p["commission_total"] == 7000 and p["commission_owed"] == 4500 and p["net_revenue"] == 13000
    assert first_creator(client)["crm_status"] == "Partnered"
    p = client.put(f"/api/partnerships/{p['id']}", json={"creator_id": c["id"], "product_id": product["id"],
                                                         "commission_pct": 50, "revenue": 10000, "amount_paid": 9000,
                                                         "payment_status": "paid"}).json()
    assert p["commission_total"] == 5000 and p["commission_owed"] == 0
    assert client.get("/api/partnerships").json()["totals"]["revenue"] == 10000
    assert client.post("/api/partnerships", json={"creator_id": 99999, "product_id": product["id"]}).status_code == 404


# ------------------------------------------------------------------ exports, dashboard
def test_exports_csv_and_xlsx_have_all_columns(client):
    run = fake_search(client)
    client.post(f"/api/creators/{first_creator(client)['id']}/notes", json={"text": "=HYPERLINK(\"http://x\")"})
    csv = client.get("/api/export", params={"scope": "search", "run_id": run["id"], "fmt": "csv"})
    df = pd.read_csv(io.BytesIO(csv.content))
    assert list(df.columns) == COLUMNS and len(df) == 6
    assert "Data type" not in df.columns and "DEMO DATA" not in csv.text
    assert ",85280," in csv.text and "85280.0" not in csv.text  # whole numbers even with empty rows
    assert df["Notes"].dropna().iloc[0].startswith("'=")  # formula injection neutralised
    xlsx = client.get("/api/export", params={"scope": "qualified", "fmt": "xlsx"})
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    sheet = pd.read_excel(io.BytesIO(xlsx.content))
    assert list(sheet.columns) == COLUMNS and len(sheet) == run["qualified"]
    assert sheet["Business email"].notna().all() and "follower_fit" in sheet["Score breakdown"].iloc[0]
    ids = ",".join(str(r["id"]) for r in run["results"][:2])
    assert len(pd.read_csv(io.BytesIO(client.get("/api/export", params={"scope": "selected", "ids": ids, "fmt": "csv"}).content))) == 2
    assert len(pd.read_csv(io.BytesIO(client.get("/api/export", params={"scope": "all", "fmt": "csv"}).content))) == 6
    assert client.get("/api/export", params={"fmt": "pdf"}).status_code == 422


def test_dashboard_counts_come_from_real_records(client):
    empty = client.get("/api/dashboard").json()
    assert empty["creators_total"] == 0 and empty["searches"] == 0 and empty["clients"] == 0
    run = fake_search(client)
    setup, ids = make_client_setup(client)
    client.post("/api/outreach/draft", json={"creator_id": ids[0]})
    d = client.get("/api/dashboard").json()
    assert d["creators_total"] == 6 and "demo_creators" not in d
    assert (d["qualified"], d["needs_review"], d["rejected"]) == (run["qualified"], run["needs_review"], run["rejected"])
    assert d["with_email"] == 5 and d["searches"] == 2 and d["clients"] == 2 and d["active_campaigns"] == 2
    assert d["outreach"]["draft"] == 1 and d["cost"]["best_known_usd"] == 0
    assert client.get("/api/dashboard", params={"campaign_id": setup["acme"]["campaign"]["id"]}).json()["creators_total"] == 4
    assert client.get("/api/dashboard", params={"date_to": "2000-01-01"}).json()["creators_total"] == 0


# ---------------------------------------------------------------------------- settings
def test_settings_validation_and_rescoring(client):
    assert client.put("/api/settings", json={"fx": {"usd_inr": -4}}).status_code == 422
    assert client.put("/api/settings", json={"filters": {"min_followers": "lots"}}).status_code == 422
    out = client.put("/api/settings", json={"fx": {"usd_inr": 88.5}, "filters": {"min_followers": 20000, "hacker": 1},
                                            "scoring_weights": {"contact": 30}}).json()
    assert out["fx"]["usd_inr"] == 88.5 and out["fx"]["updated_at"] and out["fx"]["source"] == "entered manually"
    assert out["filters"]["min_followers"] == 20000 and out["filters"]["max_followers"] == 100000
    assert "hacker" not in out["filters"] and out["scoring_weights"]["contact"] == 30
    assert "provider_mode" not in out and out["monthly_budget_inr"] == 0  # safe default: never spend beyond free allowances


# ----------------------------------------------------------------- signing key storage
def test_signing_key_is_generated_once_kept_in_the_database_and_never_exposed(anon, db, monkeypatch):
    from app.core import security
    from app.models import Setting

    monkeypatch.setattr(config_module.config, "secret_key", "")
    monkeypatch.setattr(security, "_cached_secret", None)
    res = anon.post("/api/auth/setup", json={"email": "a@test.local", "name": "A", "password": PASSWORD})
    token = res.json()["token"]
    stored = db.get(Setting, "_secret_key").value
    assert len(stored) >= 40

    # A different server instance (empty cache) must accept the same session.
    monkeypatch.setattr(security, "_cached_secret", None)
    anon.headers["Authorization"] = f"Bearer {token}"
    assert anon.get("/api/auth/me").status_code == 200
    assert db.get(Setting, "_secret_key").value == stored  # not regenerated

    settings = anon.get("/api/settings").json()
    assert "_secret_key" not in settings and stored not in str(settings)
    assert stored not in anon.get("/api/health").text
    assert anon.put("/api/settings", json={"sender_name": "x"}).status_code == 200
    assert db.get(Setting, "_secret_key").value == stored


def test_old_demo_records_are_removed_on_start_and_real_ones_kept(client, db):
    from app.main import _remove_demo_records
    from app.models import CreatorContact, Setting

    run = fake_search(client)  # real-style records, must survive
    old = Creator(username="demo_fitness_aarav", is_demo=True, niche="fitness")
    old.contacts.append(CreatorContact(type="email", value="hello@demo.example"))
    db.add(old)
    db.add(SearchRun(profile_provider="demo", is_demo=True, collected=6))
    db.add(Setting(key="provider_mode", value="mock"))
    db.commit()
    cid = client.post("/api/campaigns", json={"name": "Old"}).json()["id"]
    client.post(f"/api/campaigns/{cid}/creators", json={"creator_ids": [old.id]})
    client.post("/api/outreach/draft", json={"creator_id": old.id})

    _remove_demo_records()
    db.expire_all()
    assert db.query(Creator).filter(Creator.username == "demo_fitness_aarav").count() == 0
    assert db.query(CreatorContact).filter(CreatorContact.value == "hello@demo.example").count() == 0
    assert db.query(SearchRun).filter(SearchRun.is_demo.is_(True)).count() == 0
    assert db.get(Setting, "provider_mode") is None
    assert client.get(f"/api/campaigns/{cid}").json()["creators"] == 0
    assert client.get("/api/outreach").json() == []
    assert client.get("/api/creators").json()["total"] == run["discovered"]
    _remove_demo_records()  # safe to run again
