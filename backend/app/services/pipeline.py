"""Search pipeline: discover -> dedupe -> cache check -> collect -> normalize -> analyze -> record."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import integrations
from ..core.config import config
from ..integrations.apify_provider import ApifyClient
from ..integrations.base import FreeAllowanceExhausted, Handle, ProviderAuthError, ProviderError
from ..models import Activity, Creator, CreatorContact, CreatorSnapshot, SearchResult, SearchRun, utcnow
from . import analysis, costs
from .normalize import median_views, normalize_profile, reel_view_counts
from .settings_store import get_settings, set_setting

log = logging.getLogger("creator_finder.pipeline")
AUTO_STATUSES = {"New", "Needs Review", "Qualified", "Not Qualified"}
VERDICT_TO_CRM = {"qualified": "Qualified", "needs_review": "Needs Review", "rejected": "Not Qualified"}


def creator_profile(c: Creator) -> dict:
    """The stored fields, in the shape the analysis functions expect."""
    return {
        "username": c.username, "full_name": c.full_name, "profile_url": c.profile_url,
        "biography": c.biography, "followers": c.followers, "external_urls": c.external_urls or [],
        "business_category": c.business_category, "is_private": c.is_private,
        "captions": c.captions or [], "reels_analyzed": c.reels_analyzed,
        "median_reel_views": c.median_reel_views, "engagement_rate": c.engagement_rate,
    }


def analyze_creator(db: Session, c: Creator, settings: dict, filters: dict | None = None,
                    niche: str | None = None, sub_niche: str | None = None) -> tuple[str, list[str]]:
    """(Re)compute selling status, score and verdict from stored data."""
    filters = {**settings["filters"], **(filters or {})}
    profile = creator_profile(c)
    collected = c.last_collected_at is not None
    if collected:
        c.selling_status, c.selling_reasons = analysis.classify_selling(profile)
    else:
        c.selling_status, c.selling_reasons = "UNKNOWN", ["Profile data has not been collected."]
    contacts = [{"type": x.type, "value": x.value, "validation_status": x.validation_status} for x in c.contacts]
    status = c.effective_selling_status
    scored = analysis.lead_score(profile, status, contacts, filters, settings["scoring_weights"],
                                 niche if niche is not None else c.niche,
                                 sub_niche if sub_niche is not None else c.sub_niche, collected)
    c.lead_score, c.score_breakdown, c.confidence = scored["score"], scored["breakdown"], scored["confidence"]
    c.verdict, c.verdict_reasons = analysis.qualify(profile, status, contacts, filters, collected)
    if (c.crm_status or "New") in AUTO_STATUSES:  # a brand-new record has no status yet
        c.crm_status = VERDICT_TO_CRM[c.verdict]
    return c.verdict, c.verdict_reasons


def _apply_profile(db: Session, c: Creator, p: dict, provider: str, settings: dict, niche: str, sub_niche: str):
    for key in ("full_name", "profile_url", "biography", "followers", "following", "posts_count",
                "profile_pic_url", "external_urls", "business_category", "is_verified", "is_private",
                "captions", "reel_views", "reels_analyzed", "median_reel_views", "engagement_rate",
                "related_usernames"):
        setattr(c, key, p[key])
    c.country = p["country"] or c.country
    c.language = p["language"] or c.language
    c.niche = niche or c.niche
    c.sub_niche = sub_niche or c.sub_niche
    c.is_demo = p["is_demo"]
    c.data_provider = provider
    c.last_collected_at = utcnow()
    existing = {(x.type, x.value) for x in c.contacts}
    for contact in analysis.extract_contacts(p, settings.get("collect_phone", False)):
        if (contact["type"], contact["value"]) not in existing:
            c.contacts.append(CreatorContact(**contact))
    c.snapshots.append(CreatorSnapshot(provider=provider, followers=c.followers,
                                       median_reel_views=c.median_reel_views, engagement_rate=c.engagement_rate))


def is_cached(c: Creator | None, cache_days: int) -> bool:
    return bool(c and c.last_collected_at and c.last_collected_at >= utcnow() - timedelta(days=cache_days))


def apify_gate(db: Session, settings: dict, n_to_fetch: int, n_reel_creators: int | None = None, n_discovery: int = 0) -> dict:
    """Decide whether a live Apify call is allowed, without making a paid call."""
    estimate = costs.estimate_fetch(n_to_fetch, settings, n_reel_creators, n_discovery)
    info: dict = {"allowed": True, "estimate": estimate, "limits": None, "reasons": []}
    if settings.get("provider_mode") != "live":
        info["allowed"] = False
        info["reasons"].append("Live providers are switched off (Settings → Provider mode). Demo mode is active.")
        return info
    if not config.apify_token:
        info["allowed"] = False
        info["reasons"].append("APIFY_TOKEN is not configured on the server.")
        return info
    client = ApifyClient(config.apify_token, max_retries=2)
    try:
        info["limits"] = client.limits()
        prices = client.prices()
    except ProviderAuthError as exc:
        info["allowed"] = False
        info["reasons"].append(str(exc))
        return info
    if prices.get("usd_per_profile") is not None:  # refresh pricing from the provider itself
        pricing = {**prices, "source": "Apify Actor pricing API", "updated_at": utcnow().isoformat()}
        set_setting(db, "apify_pricing", pricing)
        db.commit()
        settings["apify_pricing"] = pricing
        info["estimate"] = estimate = costs.estimate_fetch(n_to_fetch, settings, n_reel_creators, n_discovery)
    limits = info["limits"]
    est = estimate["estimated_usd"]
    if limits and est is not None and est > limits["remaining_usd"]:
        info["allowed"] = False
        info["reasons"].append(
            f"Apify's remaining free allowance (${limits['remaining_usd']}) is below this search's estimate (${est}). "
            "No paid call was made."
        )
    info["budget"] = budget = costs.budget_state(db, settings, est or 0.0, limits["limit_usd"] if limits else None)
    if budget["level"] == "blocked":
        info["allowed"] = False
        info["reasons"].append(
            f"This would take cash spend to ₹{budget['cash_spend_inr_after']}, above the monthly budget of ₹{budget['monthly_budget_inr']}."
        )
    return info


def passes_cheap_checks(c: Creator, filters: dict) -> bool:
    """Checks that need only the profile. Reel views cost extra, so they are only
    collected for creators that get past these."""
    if c.last_collected_at is None or c.followers is None:
        return False
    if c.is_private and filters.get("require_public", True):
        return False
    if not filters["min_followers"] <= c.followers <= filters["max_followers"]:
        return False
    if (filters.get("require_email", True) and not filters.get("no_email_to_review", True)
            and not any(x.type == "email" for x in c.contacts)):
        return False  # only when a missing email is an outright rejection
    if filters.get("exclude_selling", True):
        status = (c.selling_override or {}).get("status") or analysis.classify_selling(creator_profile(c))[0]
        if status == "SELLING":
            return False
    return True


def run_search(db: Session, user, req: dict) -> dict:
    """Run one search. Returns either {"needs_confirmation": ...} or the finished run."""
    settings = get_settings(db)
    filters = {**settings["filters"], **{k: v for k, v in (req.get("filters") or {}).items() if v is not None}}
    limit = max(1, min(int(req.get("max_profiles") or settings["max_profiles_per_search"]),
                       int(settings["max_profiles_per_search"])))
    source, provider_name = req.get("discovery_source", "demo"), req.get("profile_provider", "demo")
    niche, sub_niche = (req.get("niche") or "").strip(), (req.get("sub_niche") or "").strip()
    messages: list[str] = []

    discovery = integrations.get_discovery(source)
    paid_discovery = getattr(discovery, "is_paid", False)
    if discovery.is_external and settings.get("provider_mode") != "live":
        raise ProviderError("Live discovery is switched off. Use Demo data or Manual import, or enable live mode in Settings.")
    if (discovery.is_external or provider_name == "apify") and not req.get("confirmed"):
        upper = limit
        if source == "manual":
            names = [h.username for h in integrations.get_discovery("manual").discover(req, limit).handles]
            known = {c.username: c for c in db.query(Creator).filter(Creator.username.in_(names)).all()}
            upper = sum(1 for n in names if req.get("refresh") or not is_cached(known.get(n), settings["cache_days"]))
        if provider_name == "apify" or paid_discovery:
            gate = apify_gate(db, settings, upper if provider_name == "apify" else 0,
                              None if provider_name == "apify" else 0, limit if paid_discovery else 0)
        else:
            gate = {"allowed": True, "estimate": None, "reasons": [], "limits": None}
        return {"needs_confirmation": True, "external_calls": [n for n, on in (
            (f"{'Apify hashtag' if paid_discovery else source} search", discovery.is_external),
            ("Apify profile and reel collection", provider_name == "apify")) if on],
            "max_profiles": upper, **gate}

    disc_est = 0.0
    if paid_discovery:  # paid search: check the allowance and budget before spending anything
        gate = apify_gate(db, settings, 0, 0, limit)
        if not gate["allowed"]:
            raise ProviderError(" ".join(gate["reasons"]) + " The hashtag search was not run.")
        disc_est = gate["estimate"]["estimated_usd"] or 0.0
        settings = get_settings(db)
    try:
        found = discovery.discover(req, limit)
    except FreeAllowanceExhausted as exc:
        set_setting(db, "provider_mode", "mock")
        db.commit()
        raise ProviderError(f"{exc} Live mode has been switched back to demo mode. No payment was made.") from None
    messages += found.messages
    handles: dict[str, Handle] = {}
    for h in found.handles:  # duplicate removal, keeps first source
        handles.setdefault(h.username, h)

    # Skip accounts the search snippet already shows are far outside the follower range.
    # A single reel is only a hint of a creator's usual views, so the view bounds are loose.
    def plausible(h: Handle) -> bool:
        if not discovery.is_external:
            return True
        if h.est_followers is not None and not filters["min_followers"] * 0.5 <= h.est_followers <= filters["max_followers"] * 2:
            return False
        if h.est_views is not None and not filters["min_views"] * 0.25 <= h.est_views <= filters["max_views"] * 4:
            return False
        return True
    skipped = [h.username for h in handles.values() if not plausible(h)]
    if skipped:
        messages.append(f"{len(skipped)} creator(s) skipped before profile collection: the search result already shows "
                        "followers or reel views far outside the range. This saves the profile cost.")
    names = [u for u, h in handles.items() if plausible(h)]

    existing = {c.username: c for c in db.query(Creator).filter(Creator.username.in_(names)).all()} if names else {}
    cached = [n for n in names if not req.get("refresh") and is_cached(existing.get(n), settings["cache_days"])]
    to_fetch = [n for n in names if n not in cached]

    run = SearchRun(user_id=user.id, campaign_id=req.get("campaign_id"), discovery_source=source,
                    profile_provider=provider_name, discovered=len(handles), cached=len(cached),
                    is_demo=(source == "demo" and provider_name in ("demo", "none")),
                    params={k: req.get(k) for k in ("niche", "sub_niche", "country", "language", "category")} | {"filters": filters})

    fetched: dict[str, dict] = {}
    if to_fetch and provider_name == "apify":
        gate = apify_gate(db, settings, len(to_fetch))
        run.est_cost_usd = gate["estimate"]["estimated_usd"]
        if not gate["allowed"]:
            messages += gate["reasons"]
            messages.append("Collection was skipped. Profiles are saved as “not collected”; demo mode is still available.")
            provider_name = "none"
            run.est_cost_usd = None
    if to_fetch and provider_name != "none":
        provider = integrations.get_profile_provider(provider_name)
        try:
            result = provider.fetch(to_fetch)
        except FreeAllowanceExhausted as exc:
            # Never ask for payment: fall back to demo mode and say so.
            set_setting(db, "provider_mode", "mock")
            messages.append(f"{exc} Live mode has been switched back to demo mode. No payment was made.")
            result = None
        except ProviderError as exc:
            messages.append(f"Profile collection failed: {exc}")
            result = None
        if result:
            run.requested = len(to_fetch)
            run.actor_runs = result.actor_runs
            run.actual_cost_usd = result.actual_cost_usd
            run.failed = len(result.failed)
            messages += result.messages
            for raw in result.profiles:
                p = normalize_profile(raw)
                if p:
                    fetched[p["username"]] = p

    creators: dict[str, Creator] = {}
    for name in names:
        c = existing.get(name)
        if not c:
            c = Creator(username=name, profile_url=f"https://www.instagram.com/{name}/", source=handles[name].source,
                        niche=niche, sub_niche=sub_niche)
            db.add(c)
            c.activities.append(Activity(user_id=user.id, user_name=user.name, action="created",
                                         detail=f"Found via {handles[name].source}"))
        if name in fetched:
            _apply_profile(db, c, fetched[name], provider_name, settings, niche, sub_niche)
            if provider_name == "apify":
                c.reels_collected_at = None  # fresh profile: reel views need collecting again
        creators[name] = c

    # Stage 2 (Apify only): the profile Actor has no reel view counts, so fetch
    # reels, but only for creators that already pass the cheaper checks.
    if provider_name == "apify":
        wanted = [n for n, c in creators.items() if c.data_provider == "apify" and c.reels_collected_at is None
                  and passes_cheap_checks(c, filters)]
        collected_now = sum(1 for c in creators.values() if c.data_provider == "apify" and c.last_collected_at)
        if wanted:
            gate = apify_gate(db, settings, 0, len(wanted))
            profile_est = costs.estimate_fetch(len(to_fetch), settings, 0)["estimated_usd"] if run.requested else 0.0
            reel_est = gate["estimate"]["estimated_usd"]
            if not gate["allowed"]:
                messages += gate["reasons"]
                messages.append(f"Reel views were not collected for {len(wanted)} creator(s); they are marked for review.")
            else:
                if profile_est is not None and reel_est is not None:
                    run.est_cost_usd = round(profile_est + reel_est, 4)
                try:
                    reels, reel_result = integrations.get_reel_provider("apify").fetch(wanted, int(settings["reels_per_creator"]))
                except FreeAllowanceExhausted as exc:
                    set_setting(db, "provider_mode", "mock")
                    messages.append(f"{exc} Live mode has been switched back to demo mode. No payment was made.")
                    reels, reel_result = {}, None
                except ProviderError as exc:
                    messages.append(f"Reel collection failed: {exc}")
                    reels, reel_result = {}, None
                if reel_result:
                    run.actor_runs = (run.actor_runs or 0) + reel_result.actor_runs
                    if reel_result.actual_cost_usd is not None:
                        run.actual_cost_usd = round((run.actual_cost_usd or 0) + reel_result.actual_cost_usd, 6)
                    messages += reel_result.messages
                    for name in wanted:
                        if name in reel_result.failed:
                            continue
                        c = creators[name]
                        views = reel_view_counts(reels.get(name, []))
                        c.reel_views, c.reels_analyzed, c.median_reel_views = views, len(views), median_views(views)
                        c.reels_collected_at = utcnow()
                        if c.snapshots:
                            c.snapshots[-1].median_reel_views = c.median_reel_views
                    messages.append(
                        f"Reel views were collected for {len(wanted)} of {collected_now} creator(s): only those that passed "
                        "the profile checks first. This keeps the cost down."
                    )
        elif run.requested and run.est_cost_usd is not None:
            run.est_cost_usd = costs.estimate_fetch(len(to_fetch), settings, 0)["estimated_usd"]

    counts = {"qualified": 0, "needs_review": 0, "rejected": 0}
    for name, c in creators.items():
        verdict, reasons = analyze_creator(db, c, settings, filters, niche or None, sub_niche or None)
        counts[verdict] += 1
        db.flush()
        run.results.append(SearchResult(creator_id=c.id, verdict=verdict, reasons=reasons, from_cache=name in cached))

    if paid_discovery:  # the search itself is a provider charge too
        run.actor_runs = (run.actor_runs or 0) + found.actor_runs
        if found.actual_cost_usd is not None:
            run.actual_cost_usd = round((run.actual_cost_usd or 0) + found.actual_cost_usd, 6)
        run.est_cost_usd = round((run.est_cost_usd or 0) + disc_est, 4)
    run.collected = len(fetched)
    run.qualified, run.needs_review, run.rejected = counts["qualified"], counts["needs_review"], counts["rejected"]
    run.messages = messages
    db.add(run)
    db.commit()
    return {"needs_confirmation": False, "run_id": run.id}
