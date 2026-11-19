from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import team_user
from ..integrations.base import ProviderError
from ..models import Campaign, SearchRun, User
from ..services.pipeline import run_search
from ..services.settings_store import audit
from .serializers import run_out

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class Filters(BaseModel):
    min_followers: int | None = Field(default=None, ge=0)
    max_followers: int | None = Field(default=None, ge=0)
    min_views: int | None = Field(default=None, ge=0)
    max_views: int | None = Field(default=None, ge=0)
    min_reels: int | None = Field(default=None, ge=0, le=50)
    require_email: bool | None = None
    no_email_to_review: bool | None = None
    require_public: bool | None = None
    exclude_selling: bool | None = None


class SearchIn(BaseModel):
    discovery_source: str = Field(default="hashtag", pattern="^(hashtag|manual|duckduckgo)$")
    profile_provider: str = Field(default="apify", pattern="^(apify|none)$")
    niche: str = Field(default="", max_length=80)
    sub_niche: str = Field(default="", max_length=80)
    country: str = Field(default="", max_length=80)
    language: str = Field(default="", max_length=60)
    category: str = Field(default="", max_length=120)
    usernames: str = Field(default="", max_length=20000)
    hashtags: str = Field(default="", max_length=300)
    campaign_id: int | None = None
    max_profiles: int | None = Field(default=None, ge=1, le=500)
    filters: Filters = Filters()
    refresh: bool = False
    confirmed: bool = False  # must be true before any external call is made


@router.post("/run")
def run(body: SearchIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    if body.campaign_id and not db.get(Campaign, body.campaign_id):
        raise HTTPException(404, "Campaign not found")
    f = body.filters
    if f.min_followers and f.max_followers and f.min_followers > f.max_followers:
        raise HTTPException(422, "Minimum followers is larger than maximum followers")
    if f.min_views and f.max_views and f.min_views > f.max_views:
        raise HTTPException(422, "Minimum views is larger than maximum views")
    try:
        result = run_search(db, user, body.model_dump())
    except ProviderError as exc:
        raise HTTPException(400, str(exc)) from None
    if result["needs_confirmation"]:
        return result
    if body.discovery_source != "manual" or body.profile_provider == "apify":
        audit(db, user, "search.external", f"run {result['run_id']} via {body.discovery_source}/{body.profile_provider}")
        db.commit()
    return {"needs_confirmation": False, "run": run_out(db.get(SearchRun, result["run_id"]), with_results=True)}


@router.get("/runs")
def runs(db: Session = Depends(get_db), _: User = Depends(team_user), limit: int = 30):
    rows = db.query(SearchRun).order_by(SearchRun.created_at.desc()).limit(min(limit, 200)).all()
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}")
def run_detail(run_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    row = db.get(SearchRun, run_id)
    if not row:
        raise HTTPException(404, "Search not found")
    return run_out(row, with_results=True)
