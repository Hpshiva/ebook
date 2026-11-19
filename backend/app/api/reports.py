from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.config import DEFAULT_SETTINGS, config
from ..core.db import get_db
from ..core.security import admin_user, current_user, team_user
from ..integrations.apify_provider import ApifyClient
from ..integrations.base import ProviderError
from ..models import (AuditLog, Setting, Campaign, CampaignCreator, Client, Creator, CreatorContact, OutreachMessage,
                      SearchResult, SearchRun, User)
from ..services import costs
from ..services.exports import build_export, creator_row
from ..services.settings_store import (APIFY_TOKEN_ROW, apify_token_source, audit, ensure_apify_token, get_settings,
                                       set_setting, update_settings)
from .campaigns import scoped_campaign

router = APIRouter(prefix="/api", tags=["reports"])


def _range(date_from: date | None, date_to: date | None):
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else None
    return start, end


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(team_user), date_from: date | None = None,
              date_to: date | None = None, campaign_id: int | None = None):
    start, end = _range(date_from, date_to)
    q = db.query(Creator)
    if campaign_id:
        q = q.filter(Creator.id.in_(db.query(CampaignCreator.creator_id).filter(CampaignCreator.campaign_id == campaign_id)))
    if start:
        q = q.filter(Creator.created_at >= start)
    if end:
        q = q.filter(Creator.created_at < end)
    creators = q.all()
    ids = {c.id for c in creators}
    with_email = {cid for (cid,) in db.query(CreatorContact.creator_id).filter(CreatorContact.type == "email")} & ids

    runs = db.query(SearchRun)
    if campaign_id:
        runs = runs.filter(SearchRun.campaign_id == campaign_id)
    if start:
        runs = runs.filter(SearchRun.created_at >= start)
    if end:
        runs = runs.filter(SearchRun.created_at < end)
    runs = runs.all()
    live = runs
    best_cost = sum((r.actual_cost_usd if r.actual_cost_usd is not None else (r.est_cost_usd or 0)) for r in live)

    messages = [m for m in db.query(OutreachMessage).all() if m.creator_id in ids]
    statuses: dict[str, int] = {}
    for c in creators:
        statuses[c.crm_status] = statuses.get(c.crm_status, 0) + 1
    settings = get_settings(db)
    return {
        "creators_total": len(creators),
        "qualified": sum(1 for c in creators if c.verdict == "qualified"),
        "needs_review": sum(1 for c in creators if c.verdict == "needs_review"),
        "rejected": sum(1 for c in creators if c.verdict == "rejected"),
        "with_email": len(with_email),
        "searches": len(runs),
        "active_campaigns": db.query(Campaign).filter(Campaign.status == "Active").count(),
        "clients": db.query(Client).count(),
        "crm_statuses": statuses,
        "outreach": {s: sum(1 for m in messages if m.status == s) for s in ("draft", "contacted", "replied", "no_reply")},
        "follow_ups_due": sum(1 for c in creators if c.follow_up_date and c.follow_up_date <= date.today()),
        "cost": {"best_known_usd": round(best_cost, 4), "best_known_inr": costs.to_inr(best_cost, settings),
                 "has_actuals": any(r.actual_cost_usd is not None for r in live), "live_searches": len(live)},
        "apify_token_configured": bool(config.apify_token),
    }


@router.get("/export")
def export(db: Session = Depends(get_db), user: User = Depends(current_user), fmt: str = "xlsx",
           scope: str = "qualified", ids: str = "", run_id: int | None = None, campaign_id: int | None = None):
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(422, "Format must be csv or xlsx")
    campaign_name = ""
    if user.role == "client" and scope != "campaign":
        raise HTTPException(403, "You do not have access to this")
    if scope == "campaign":
        if not campaign_id:
            raise HTTPException(422, "campaign_id is required")
        campaign = scoped_campaign(db, campaign_id, user)
        campaign_name = campaign.name
        links = [l for l in campaign.links if l.shortlisted] if user.role == "client" else campaign.links
        creators = [l.creator for l in links]
    elif scope == "selected":
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()][:5000]
        creators = db.query(Creator).filter(Creator.id.in_(wanted)).all() if wanted else []
    elif scope == "search":
        if not run_id:
            raise HTTPException(422, "run_id is required")
        creators = [r.creator for r in db.query(SearchResult).filter(SearchResult.run_id == run_id).all()]
    elif scope in ("qualified", "needs_review", "rejected"):
        creators = db.query(Creator).filter(Creator.verdict == scope).all()
    elif scope == "all":
        creators = db.query(Creator).all()
    else:
        raise HTTPException(422, "Unknown export scope")
    creators.sort(key=lambda c: c.lead_score or 0, reverse=True)
    # Client exports never include our internal notes.
    rows = [creator_row(c, campaign_name, notes="" if user.role == "client" else None) for c in creators]
    data, mime, ext = build_export(rows, fmt)
    audit(db, user, "export", f"{scope} {len(rows)} rows as {ext}")
    db.commit()
    return Response(data, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="creator-finder-{scope}.{ext}"'})


@router.get("/costs")
def cost_report(db: Session = Depends(get_db), _: User = Depends(team_user), check_provider: bool = False):
    ensure_apify_token(db)
    settings = get_settings(db)
    limits, provider_note = None, None
    if check_provider:  # only on request: this is an external (free) call to Apify
        if not config.apify_token:
            provider_note = "APIFY_TOKEN is not configured, so no free allowance can be read."
        else:
            try:
                limits = ApifyClient(config.apify_token, max_retries=2).limits()
                provider_note = None if limits else "Apify did not return usage limits."
            except ProviderError as exc:
                provider_note = str(exc)
    month = costs.usage_summary(db)
    all_time = costs.usage_summary(db, since=datetime(2000, 1, 1))
    for block in (month, all_time):
        for key in ("estimated_cost", "actual_cost", "best_known_cost", "cost_per_profile", "cost_per_qualified"):
            block[f"{key}_inr"] = costs.to_inr(block[f"{key}_usd"], settings)
    return {
        "month": month, "all_time": all_time,
        "budget": costs.budget_state(db, settings, 0.0, limits["limit_usd"] if limits else None),
        "fx": settings["fx"], "apify_pricing": settings["apify_pricing"], "apify_limits": limits,
        "provider_note": provider_note,
        "apify_token_configured": bool(config.apify_token),
        "max_profiles_per_search": settings["max_profiles_per_search"],
        "recent_runs": [
            {"id": r.id, "created_at": r.created_at.isoformat(), "source": r.discovery_source,
             "provider": r.profile_provider, "requested": r.requested,
             "collected": r.collected, "cached": r.cached, "qualified": r.qualified, "actor_runs": r.actor_runs,
             "est_cost_usd": r.est_cost_usd, "actual_cost_usd": r.actual_cost_usd}
            for r in db.query(SearchRun).order_by(SearchRun.created_at.desc()).limit(25).all()],
    }


class SettingsPatch(BaseModel):
    filters: dict | None = None
    scoring_weights: dict | None = None
    cache_days: int | None = None
    reels_per_creator: int | None = None
    max_profiles_per_search: int | None = None
    collect_phone: bool | None = None
    monthly_budget_inr: float | None = None
    budget_warn_pct: float | None = None
    fx: dict | None = None
    sender_name: str | None = None


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), _: User = Depends(team_user)):
    return _settings_out(db, get_settings(db))


def _settings_out(db: Session, settings: dict) -> dict:
    ensure_apify_token(db)
    return {**settings, "apify_token_configured": bool(config.apify_token), "apify_token_source": apify_token_source()}


class TokenIn(BaseModel):
    token: str


@router.put("/settings/apify-token")
def save_apify_token(body: TokenIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    """Save the Apify token in the app's database. It is checked with Apify first and is never returned by any endpoint."""
    token = body.token.strip()
    if not 20 <= len(token) <= 200 or any(c.isspace() for c in token):
        raise HTTPException(422, "That does not look like an Apify token")
    if config.apify_token_from_env:
        raise HTTPException(409, "A token is already set in the server environment; it takes priority")
    from ..integrations.base import ProviderAuthError

    limits = None
    try:
        limits = ApifyClient(token, max_retries=2).limits()
    except ProviderAuthError:
        raise HTTPException(400, "Apify rejected this token. Copy it again from Apify → Settings → API & Integrations.") from None
    except ProviderError:
        pass  # Apify unreachable right now: save it, the first search will verify it
    set_setting(db, APIFY_TOKEN_ROW, token)
    audit(db, admin, "apify_token.save", "Apify token saved in the app")
    db.commit()
    return {**_settings_out(db, get_settings(db)), "apify_limits": limits}


@router.delete("/settings/apify-token")
def remove_apify_token(db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    row = db.get(Setting, APIFY_TOKEN_ROW)
    if row:
        db.delete(row)
        audit(db, admin, "apify_token.remove", "Apify token removed from the app")
        db.commit()
    return _settings_out(db, get_settings(db))


@router.put("/settings")
def write_settings(body: SettingsPatch, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    patch = body.model_dump(exclude_none=True)
    for key, low, high in (("cache_days", 0, 365), ("max_profiles_per_search", 1, 500), ("reels_per_creator", 2, 30),
                           ("monthly_budget_inr", 0, 10_000_000), ("budget_warn_pct", 1, 100)):
        if key in patch and not low <= patch[key] <= high:
            raise HTTPException(422, f"{key} must be between {low} and {high}")
    for key in ("filters", "scoring_weights"):
        if key in patch:
            allowed = DEFAULT_SETTINGS[key]
            clean = {}
            for k, v in patch[key].items():
                if k not in allowed:
                    continue
                if isinstance(allowed[k], bool):
                    clean[k] = bool(v)
                elif isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
                    clean[k] = v
                else:
                    raise HTTPException(422, f"{key}.{k} must be a non-negative number")
            patch[key] = clean
    if "fx" in patch:
        rate = patch["fx"].get("usd_inr")
        if not isinstance(rate, (int, float)) or not 1 <= rate <= 1000:
            raise HTTPException(422, "Exchange rate must be a number between 1 and 1000")
        patch["fx"] = {"usd_inr": float(rate)}
    out = update_settings(db, patch)
    audit(db, admin, "settings.update", ", ".join(patch.keys()))
    db.commit()
    return _settings_out(db, out)


@router.get("/audit")
def audit_log(db: Session = Depends(get_db), _: User = Depends(admin_user), limit: int = 100):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    return [{"id": r.id, "user_email": r.user_email, "action": r.action, "detail": r.detail,
             "created_at": r.created_at.isoformat()} for r in rows]
