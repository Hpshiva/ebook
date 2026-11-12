"""Cost and usage tracking. Estimates and provider-reported actuals are kept apart."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import SearchRun, utcnow

LARGE_SEARCH = 25


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_summary(db: Session, since: datetime | None = None, campaign_id: int | None = None) -> dict:
    q = db.query(SearchRun).filter(SearchRun.created_at >= (since or month_start()))
    if campaign_id:
        q = q.filter(SearchRun.campaign_id == campaign_id)
    runs = q.all()
    live = [r for r in runs if not r.is_demo]
    actual = [r.actual_cost_usd for r in live if r.actual_cost_usd is not None]
    est = [r.est_cost_usd for r in live if r.est_cost_usd is not None]
    # Best known figure per run: the provider's actual charge, else our estimate.
    best = sum((r.actual_cost_usd if r.actual_cost_usd is not None else (r.est_cost_usd or 0)) for r in live)
    collected = sum(r.collected for r in live)
    qualified = sum(r.qualified for r in live)
    return {
        "searches": len(runs),
        "demo_searches": len(runs) - len(live),
        "profiles_requested": sum(r.requested for r in runs),
        "profiles_collected": sum(r.collected for r in runs),
        "profiles_cached": sum(r.cached for r in runs),
        "profiles_failed": sum(r.failed for r in runs),
        "actor_runs": sum(r.actor_runs for r in runs),
        "live_profiles_collected": collected,
        "live_qualified": qualified,
        "estimated_cost_usd": round(sum(est), 4) if est else None,
        "actual_cost_usd": round(sum(actual), 4) if actual else None,
        "best_known_cost_usd": round(best, 4),
        "cost_per_profile_usd": round(best / collected, 5) if collected and best else None,
        "cost_per_qualified_usd": round(best / qualified, 5) if qualified and best else None,
    }


def to_inr(usd: float | None, settings: dict) -> float | None:
    return None if usd is None else round(usd * float(settings["fx"]["usd_inr"]), 2)


def budget_state(db: Session, settings: dict, extra_usd: float = 0.0, free_allowance_usd: float | None = None) -> dict:
    """Cash exposure this month = known provider cost beyond the provider's free allowance."""
    used = usage_summary(db)["best_known_cost_usd"]
    free = free_allowance_usd or 0.0
    cash_now = max(0.0, used - free)
    cash_after = max(0.0, used + extra_usd - free)
    budget = float(settings.get("monthly_budget_inr") or 0)
    after_inr = to_inr(cash_after, settings) or 0.0
    pct = (after_inr / budget * 100) if budget else (100.0 if after_inr > 0 else 0.0)
    if after_inr > budget:
        level = "blocked"
    elif budget and pct >= float(settings.get("budget_warn_pct", 80)):
        level = "warning"
    else:
        level = "ok"
    return {
        "monthly_budget_inr": budget,
        "provider_cost_usd_this_month": round(used, 4),
        "free_allowance_usd": free_allowance_usd,
        "cash_spend_inr_now": to_inr(cash_now, settings),
        "cash_spend_inr_after": after_inr,
        "percent_of_budget": round(pct, 1),
        "level": level,
    }


def estimate_fetch(n_profiles: int, settings: dict, n_reel_creators: int | None = None, n_discovery: int = 0) -> dict:
    """Estimate for collecting profiles plus reels for `n_reel_creators` of them.

    By default every profile is assumed to reach the reel stage, which makes this an
    upper bound: in practice only creators that pass the follower, email and selling
    checks do."""
    pricing = settings.get("apify_pricing") or {}
    price, reel_price = pricing.get("usd_per_profile"), pricing.get("usd_per_reel")
    per_creator = int(settings.get("reels_per_creator") or 0)
    n_reels = n_profiles if n_reel_creators is None else n_reel_creators
    profiles_usd = 0.0 if n_profiles == 0 else (None if price is None else n_profiles * float(price))
    if n_reels == 0:
        reels_usd = 0.0
    elif reel_price is None:
        reels_usd = None
    else:
        runs = -(-n_reels // 25)
        reels_usd = n_reels * per_creator * float(reel_price) + runs * float(pricing.get("usd_per_reel_run") or 0)
    tag_price = pricing.get("usd_per_hashtag_result")
    discovery_usd = 0.0 if n_discovery == 0 else (None if tag_price is None else n_discovery * float(tag_price))
    parts = (profiles_usd, reels_usd, discovery_usd)
    est = None if any(x is None for x in parts) else round(sum(parts), 4)
    return {
        "profiles_to_fetch": n_profiles,
        "usd_per_profile": price,
        "usd_per_reel": reel_price,
        "reels_per_creator": per_creator,
        "profiles_usd": None if profiles_usd is None else round(profiles_usd, 4),
        "reels_usd_max": None if reels_usd is None else round(reels_usd, 4),
        "discovery_results": n_discovery,
        "discovery_usd": None if discovery_usd is None else round(discovery_usd, 4),
        "pricing_source": pricing.get("source"),
        "estimated_usd": est,
        "estimated_inr": to_inr(est, settings),
        "is_estimate": True,
        "is_upper_bound": n_reel_creators is None,
        "large_search": n_profiles > LARGE_SEARCH,
    }
