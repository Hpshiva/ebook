"""Outreach drafts and partnerships. Drafts are for a human to review and send;
this app never sends email or Instagram messages itself."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import team_user
from ..models import Activity, Creator, OutreachMessage, OutreachTemplate, Partnership, Product, User, utcnow
from ..services.settings_store import get_settings
from .serializers import message_out, partnership_out

router = APIRouter(prefix="/api", tags=["outreach"])

DEFAULT_TEMPLATE = {
    "name": "Partnership intro",
    "subject": "Collaboration idea for {username}",
    "body": (
        "Hi {first_name},\n\n"
        "I came across your Instagram content about {niche} and found your work interesting.\n\n"
        "We're exploring a collaboration around a digital product that could be relevant to your audience.\n\n"
        "Would you be open to discussing a possible partnership?\n\n"
        "Best,\n{sender}\n\n"
        "If you'd prefer not to hear from us, just reply and we won't contact you again."
    ),
}
PLACEHOLDERS = ("first_name", "username", "niche", "followers", "sender", "product")
MESSAGE_STATUSES = ("draft", "contacted", "replied", "no_reply")


class _Safe(dict):
    def __missing__(self, key):  # unknown placeholders stay visible instead of crashing
        return "{" + key + "}"


def render(text: str, creator: Creator, sender: str, product: str = "") -> str:
    name = (creator.full_name or creator.username).replace("(Demo)", "").strip().split(" ")[0] or creator.username
    values = _Safe(first_name=name, username=creator.username, niche=creator.niche or "your niche",
                   followers=f"{creator.followers:,}" if creator.followers else "", sender=sender or "[your name]",
                   product=product or "our digital product")
    try:
        return text.format_map(values)
    except (ValueError, IndexError):
        return text


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str = Field(default="", max_length=255)
    body: str = Field(min_length=1, max_length=8000)


class DraftIn(BaseModel):
    creator_id: int
    template_id: int | None = None
    campaign_id: int | None = None
    product: str = Field(default="", max_length=160)


class MessagePatch(BaseModel):
    subject: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=8000)
    status: str | None = None
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


def ensure_default_template(db: Session) -> None:
    if not db.query(OutreachTemplate).count():
        db.add(OutreachTemplate(**DEFAULT_TEMPLATE))
        db.commit()


@router.get("/outreach/templates")
def templates(db: Session = Depends(get_db), _: User = Depends(team_user)):
    ensure_default_template(db)
    return {"placeholders": PLACEHOLDERS, "templates": [
        {"id": t.id, "name": t.name, "subject": t.subject, "body": t.body} for t in db.query(OutreachTemplate).all()]}


@router.post("/outreach/templates")
def create_template(body: TemplateIn, db: Session = Depends(get_db), _: User = Depends(team_user)):
    t = OutreachTemplate(**body.model_dump())
    db.add(t)
    db.commit()
    return {"id": t.id, **body.model_dump()}


@router.put("/outreach/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn, db: Session = Depends(get_db), _: User = Depends(team_user)):
    t = db.get(OutreachTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    t.name, t.subject, t.body = body.name, body.subject, body.body
    db.commit()
    return {"id": t.id, **body.model_dump()}


@router.delete("/outreach/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    t = db.get(OutreachTemplate, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    db.delete(t)
    db.commit()
    return {"deleted": True}


@router.post("/outreach/draft")
def create_draft(body: DraftIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    creator = db.get(Creator, body.creator_id)
    if not creator:
        raise HTTPException(404, "Creator not found")
    ensure_default_template(db)
    template = db.get(OutreachTemplate, body.template_id) if body.template_id else db.query(OutreachTemplate).first()
    if not template:
        raise HTTPException(404, "Template not found")
    sender = get_settings(db).get("sender_name") or user.name
    message = OutreachMessage(creator_id=creator.id, campaign_id=body.campaign_id, created_by=user.id,
                              subject=render(template.subject, creator, sender, body.product),
                              body=render(template.body, creator, sender, body.product))
    db.add(message)
    creator.activities.append(Activity(user_id=user.id, user_name=user.name, action="outreach", detail="Outreach draft created"))
    db.commit()
    return message_out(message)


@router.get("/outreach")
def list_messages(db: Session = Depends(get_db), _: User = Depends(team_user), status: str = "", creator_id: int | None = None):
    q = db.query(OutreachMessage)
    if status:
        q = q.filter(OutreachMessage.status == status)
    if creator_id:
        q = q.filter(OutreachMessage.creator_id == creator_id)
    return [message_out(m) for m in q.order_by(OutreachMessage.created_at.desc()).limit(500).all()]


@router.patch("/outreach/{message_id}")
def update_message(message_id: int, body: MessagePatch, db: Session = Depends(get_db), user: User = Depends(team_user)):
    m = db.get(OutreachMessage, message_id)
    if not m:
        raise HTTPException(404, "Message not found")
    data = body.model_dump(exclude_unset=True)
    new_status = data.get("status")
    if new_status and new_status not in MESSAGE_STATUSES:
        raise HTTPException(422, "Unknown outreach status")
    if new_status and new_status != m.status:
        creator = m.creator
        # Recording that a human sent it. Nothing is sent by this app.
        if new_status == "contacted":
            m.contacted_at = utcnow()
            if creator.crm_status in ("New", "Needs Review", "Qualified"):
                creator.crm_status = "Contacted"
        elif new_status == "replied" and creator.crm_status in ("Contacted", "Follow-up"):
            creator.crm_status = "Replied"
        creator.activities.append(Activity(user_id=user.id, user_name=user.name, action="outreach",
                                           detail=f"Outreach marked {new_status.replace('_', ' ')}"))
    for key, value in data.items():
        setattr(m, key, value)
    if "follow_up_date" in data:
        m.creator.follow_up_date = data["follow_up_date"]
    db.commit()
    return message_out(m)


@router.delete("/outreach/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    m = db.get(OutreachMessage, message_id)
    if not m:
        raise HTTPException(404, "Message not found")
    db.delete(m)
    db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------------- partnerships
class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    price: float = Field(default=0, ge=0)
    currency: str = Field(default="INR", max_length=8)


class PartnershipIn(BaseModel):
    creator_id: int
    product_id: int
    start_date: date | None = None
    commission_pct: float = Field(default=0, ge=0, le=100)
    fixed_payment: float = Field(default=0, ge=0)
    tracking_url: str = Field(default="", max_length=255)
    promo_code: str = Field(default="", max_length=60)
    clicks: int | None = Field(default=None, ge=0)
    conversions: int | None = Field(default=None, ge=0)
    revenue: float = Field(default=0, ge=0)
    amount_paid: float = Field(default=0, ge=0)
    payment_status: str = Field(default="pending", pattern="^(pending|partial|paid)$")
    notes: str = Field(default="", max_length=4000)


@router.get("/products")
def products(db: Session = Depends(get_db), _: User = Depends(team_user)):
    return [{"id": p.id, "name": p.name, "price": p.price, "currency": p.currency} for p in db.query(Product).all()]


@router.post("/products")
def create_product(body: ProductIn, db: Session = Depends(get_db), _: User = Depends(team_user)):
    p = Product(**body.model_dump())
    db.add(p)
    db.commit()
    return {"id": p.id, **body.model_dump()}


@router.get("/partnerships")
def partnerships(db: Session = Depends(get_db), _: User = Depends(team_user)):
    rows = [partnership_out(p) for p in db.query(Partnership).order_by(Partnership.created_at.desc()).all()]
    return {"items": rows, "totals": {k: round(sum(r[k] for r in rows), 2)
                                      for k in ("revenue", "commission_total", "commission_owed", "amount_paid", "net_revenue")}}


def _check(db: Session, body: PartnershipIn):
    if not db.get(Creator, body.creator_id):
        raise HTTPException(404, "Creator not found")
    if not db.get(Product, body.product_id):
        raise HTTPException(404, "Product not found")


@router.post("/partnerships")
def create_partnership(body: PartnershipIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    _check(db, body)
    p = Partnership(**body.model_dump())
    db.add(p)
    creator = db.get(Creator, body.creator_id)
    creator.crm_status = "Partnered"
    creator.activities.append(Activity(user_id=user.id, user_name=user.name, action="partnership", detail="Partnership created"))
    db.commit()
    return partnership_out(p)


@router.put("/partnerships/{partnership_id}")
def update_partnership(partnership_id: int, body: PartnershipIn, db: Session = Depends(get_db), _: User = Depends(team_user)):
    p = db.get(Partnership, partnership_id)
    if not p:
        raise HTTPException(404, "Partnership not found")
    _check(db, body)
    for key, value in body.model_dump().items():
        setattr(p, key, value)
    db.commit()
    return partnership_out(p)


@router.delete("/partnerships/{partnership_id}")
def delete_partnership(partnership_id: int, db: Session = Depends(get_db), _: User = Depends(team_user)):
    p = db.get(Partnership, partnership_id)
    if not p:
        raise HTTPException(404, "Partnership not found")
    db.delete(p)
    db.commit()
    return {"deleted": True}
