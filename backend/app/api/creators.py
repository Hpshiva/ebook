from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import team_user
from ..integrations.mock_provider import NICHES
from ..models import CRM_STATUSES, SELLING_STATUSES, Activity, Creator, CreatorContact, User, utcnow
from ..services import analysis
from ..services.pipeline import analyze_creator
from ..services.settings_store import audit, get_settings
from ..services.similar import find_similar
from .serializers import creator_out

router = APIRouter(prefix="/api", tags=["creators"])
SORTS = {
    "lead_score": Creator.lead_score, "followers": Creator.followers, "median_reel_views": Creator.median_reel_views,
    "created_at": Creator.created_at, "last_collected_at": Creator.last_collected_at, "username": Creator.username,
    "follow_up_date": Creator.follow_up_date,
}


class CreatorPatch(BaseModel):
    crm_status: str | None = None
    owner_id: int | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    follow_up_date: date | None = None
    niche: str | None = Field(default=None, max_length=80)
    country: str | None = Field(default=None, max_length=80)
    language: str | None = Field(default=None, max_length=60)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class OverrideIn(BaseModel):
    status: str | None = None  # None clears the override
    note: str = Field(default="", max_length=1000)


def get_creator(db: Session, creator_id: int) -> Creator:
    creator = db.get(Creator, creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
    return creator


def log(creator: Creator, user: User, action: str, detail: str):
    creator.activities.append(Activity(user_id=user.id, user_name=user.name, action=action, detail=detail))


def filtered_query(db: Session, search="", niche="", country="", selling_status="", crm_status="", verdict="",
                   has_email: bool | None = None, min_followers: int | None = None, max_followers: int | None = None,
                   min_score: float | None = None, tag="", include_demo=True, owner_id: int | None = None,
                   language=""):
    q = db.query(Creator)
    if search:
        like = f"%{search.strip().lower()}%"
        q = q.filter(or_(func.lower(Creator.username).like(like), func.lower(Creator.full_name).like(like),
                         func.lower(Creator.biography).like(like)))
    if niche:
        q = q.filter(func.lower(Creator.niche) == niche.lower())
    if country:
        q = q.filter(func.lower(Creator.country) == country.lower())
    if language:
        q = q.filter(func.lower(Creator.language) == language.lower())
    if crm_status:
        q = q.filter(Creator.crm_status == crm_status)
    if verdict:
        q = q.filter(Creator.verdict == verdict)
    if owner_id:
        q = q.filter(Creator.owner_id == owner_id)
    if has_email is not None:
        sub = db.query(CreatorContact.creator_id).filter(CreatorContact.type == "email")
        q = q.filter(Creator.id.in_(sub) if has_email else Creator.id.notin_(sub))
    if min_followers is not None:
        q = q.filter(Creator.followers >= min_followers)
    if max_followers is not None:
        q = q.filter(Creator.followers <= max_followers)
    if min_score is not None:
        q = q.filter(Creator.lead_score >= min_score)
    if not include_demo:
        q = q.filter(Creator.is_demo.is_(False))
    rows = None
    if selling_status or tag:  # JSON-backed fields: filter in Python for SQLite/Postgres portability
        rows = [c for c in q.all()
                if (not selling_status or c.effective_selling_status == selling_status)
                and (not tag or tag.lower() in [t.lower() for t in (c.tags or [])])]
    return q, rows


@router.get("/meta")
def meta(db: Session = Depends(get_db), _: User = Depends(team_user)):
    def distinct(col):
        return sorted({v for (v,) in db.query(col).distinct() if v})
    return {
        "crm_statuses": CRM_STATUSES, "selling_statuses": SELLING_STATUSES,
        "niches": sorted(set(NICHES) | {n.lower() for n in distinct(Creator.niche)}),
        "demo_niches": list(NICHES), "countries": distinct(Creator.country), "languages": distinct(Creator.language),
        "owners": [{"id": u.id, "name": u.name or u.email}
                   for u in db.query(User).filter(User.role != "client", User.is_active).all()],
    }


@router.get("/creators")
def list_creators(
    db: Session = Depends(get_db), _: User = Depends(team_user),
    search: str = "", niche: str = "", country: str = "", language: str = "", selling_status: str = "",
    crm_status: str = "", verdict: str = "", has_email: bool | None = None,
    min_followers: int | None = None, max_followers: int | None = None, min_score: float | None = None,
    tag: str = "", include_demo: bool = True, owner_id: int | None = None,
    sort: str = "lead_score", order: str = "desc",
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
):
    q, rows = filtered_query(db, search, niche, country, selling_status, crm_status, verdict, has_email,
                             min_followers, max_followers, min_score, tag, include_demo, owner_id, language)
    col = SORTS.get(sort, Creator.lead_score)
    if rows is None:
        total = q.count()
        ordering = col.desc().nulls_last() if order == "desc" else col.asc().nulls_last()
        items = q.order_by(ordering, Creator.id).offset((page - 1) * page_size).limit(page_size).all()
    else:
        total = len(rows)
        rows.sort(key=lambda c: (getattr(c, col.key) is None, getattr(c, col.key) or 0), reverse=False)
        if order == "desc":
            rows.sort(key=lambda c: (getattr(c, col.key) is not None, getattr(c, col.key) or 0), reverse=True)
        items = rows[(page - 1) * page_size: page * page_size]
    return {"total": total, "page": page, "page_size": page_size, "items": [creator_out(c) for c in items]}


@router.get("/creators/{creator_id}")
def creator_detail(creator_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    return creator_out(get_creator(db, creator_id), detail=True)


@router.patch("/creators/{creator_id}")
def update_creator(creator_id: int, body: CreatorPatch, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    data = body.model_dump(exclude_unset=True)
    if "crm_status" in data:
        if data["crm_status"] not in CRM_STATUSES:
            raise HTTPException(422, "Unknown CRM status")
        if data["crm_status"] != creator.crm_status:
            log(creator, user, "status", f"{creator.crm_status} → {data['crm_status']}")
    if "owner_id" in data and data["owner_id"] is not None:
        owner = db.get(User, data["owner_id"])
        if not owner or owner.role == "client":
            raise HTTPException(422, "Owner must be a team member")
        log(creator, user, "owner", f"Assigned to {owner.name or owner.email}")
    if "tags" in data and data["tags"] is not None:
        data["tags"] = list(dict.fromkeys(t.strip()[:40] for t in data["tags"] if t.strip()))
        log(creator, user, "tags", ", ".join(data["tags"]) or "cleared")
    if "follow_up_date" in data:
        log(creator, user, "follow_up", str(data["follow_up_date"] or "cleared"))
    for key, value in data.items():
        setattr(creator, key, value if value is not None or key in ("owner_id", "follow_up_date") else getattr(creator, key))
    db.commit()
    return creator_out(creator, detail=True)


@router.post("/creators/{creator_id}/notes")
def add_note(creator_id: int, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    log(creator, user, "note", body.text.strip())
    db.commit()
    return creator_out(creator, detail=True)


@router.post("/creators/{creator_id}/selling-override")
def selling_override(creator_id: int, body: OverrideIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    if body.status is None:
        creator.selling_override = None
        log(creator, user, "selling_override", "Manual override removed")
    else:
        if body.status not in SELLING_STATUSES:
            raise HTTPException(422, "Unknown selling status")
        creator.selling_override = {"status": body.status, "by": user.name or user.email, "by_id": user.id,
                                    "at": utcnow().isoformat(), "note": body.note}
        log(creator, user, "selling_override", f"Set to {body.status} (detected: {creator.selling_status}). {body.note}".strip())
    analyze_creator(db, creator, get_settings(db))
    db.commit()
    return creator_out(creator, detail=True)


@router.post("/creators/{creator_id}/reanalyze")
def reanalyze(creator_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    analyze_creator(db, creator, get_settings(db))
    db.commit()
    return creator_out(creator, detail=True)


@router.post("/creators/{creator_id}/contacts/{contact_id}/verify")
def verify_contact(creator_id: int, contact_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    """Free DNS check that the email's domain can receive mail. Does not prove the mailbox exists."""
    creator = get_creator(db, creator_id)
    contact = next((x for x in creator.contacts if x.id == contact_id), None)
    if not contact or contact.type != "email":
        raise HTTPException(404, "Email contact not found")
    result = analysis.check_mx(contact.value.rsplit("@", 1)[-1])
    if result is None:
        raise HTTPException(503, "DNS lookup failed, please try again")
    contact.validation_status = "mx_checked" if result else "domain_has_no_mail_server"
    analyze_creator(db, creator, get_settings(db))
    db.commit()
    return creator_out(creator, detail=True)


@router.delete("/creators/{creator_id}/contacts/{contact_id}")
def delete_contact(creator_id: int, contact_id: int, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    contact = next((x for x in creator.contacts if x.id == contact_id), None)
    if not contact:
        raise HTTPException(404, "Contact not found")
    creator.contacts.remove(contact)
    log(creator, user, "contact_deleted", f"Removed {contact.type}")
    audit(db, user, "contact.delete", f"{creator.username} {contact.type}")
    analyze_creator(db, creator, get_settings(db))
    db.commit()
    return creator_out(creator, detail=True)


@router.delete("/creators/{creator_id}")
def delete_creator(creator_id: int, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = get_creator(db, creator_id)
    from ..models import SearchResult

    db.query(SearchResult).filter(SearchResult.creator_id == creator.id).delete()
    audit(db, user, "creator.delete", creator.username)
    db.delete(creator)
    db.commit()
    return {"deleted": True}


@router.get("/creators/{creator_id}/similar")
def similar(creator_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    target = get_creator(db, creator_id)
    out = []
    for row in find_similar(db, target):
        other = db.get(Creator, row["creator_id"])
        out.append({**creator_out(other), "similarity": row["similarity"], "similar_reasons": row["reasons"]})
    known = {u for (u,) in db.query(Creator.username).filter(Creator.username.in_(target.related_usernames or []))}
    return {"similar": out, "not_yet_collected": [u for u in (target.related_usernames or []) if u not in known]}
