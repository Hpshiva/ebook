"""Clients and campaigns. Client-portal users are scoped to their own client here."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import current_user, team_user
from ..models import Activity, Campaign, CampaignCreator, Client, Creator, User, utcnow
from ..services.settings_store import audit
from .serializers import campaign_out, client_out, link_out

router = APIRouter(prefix="/api", tags=["campaigns"])


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact_name: str = Field(default="", max_length=160)
    email: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=4000)
    status: str = Field(default="Active", max_length=30)


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    client_id: int | None = None
    niche: str = Field(default="", max_length=80)
    product_name: str = Field(default="", max_length=160)
    target_leads: int = Field(default=0, ge=0, le=100000)
    requirements: dict = {}
    status: str = Field(default="Active", max_length=30)


class AddCreators(BaseModel):
    creator_ids: list[int] = Field(min_length=1, max_length=500)
    shortlisted: bool = False


class LinkPatch(BaseModel):
    shortlisted: bool


class Decision(BaseModel):
    approval: str = Field(pattern="^(pending|approved|rejected)$")
    note: str = Field(default="", max_length=1000)


def scoped_campaign(db: Session, campaign_id: int, user: User) -> Campaign:
    """Tenant isolation: a client user only ever reaches campaigns of their own client."""
    campaign = db.get(Campaign, campaign_id)
    if not campaign or (user.role == "client" and campaign.client_id != user.client_id):
        raise HTTPException(404, "Campaign not found")
    return campaign


# ---------------------------------------------------------------- clients (team only)
@router.get("/clients")
def list_clients(db: Session = Depends(get_db), _: User = Depends(team_user)):
    return [client_out(c) for c in db.query(Client).order_by(Client.name).all()]


@router.post("/clients")
def create_client(body: ClientIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    if db.query(Client).filter(Client.name == body.name.strip()).first():
        raise HTTPException(409, "A client with this name already exists")
    client = Client(**{**body.model_dump(), "name": body.name.strip()})
    db.add(client)
    audit(db, user, "client.create", client.name)
    db.commit()
    return client_out(client)


@router.patch("/clients/{client_id}")
def update_client(client_id: int, body: ClientIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    for key, value in body.model_dump().items():
        setattr(client, key, value)
    audit(db, user, "client.update", client.name)
    db.commit()
    return client_out(client)


@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), user: User = Depends(team_user)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    if client.campaigns or db.query(User).filter(User.client_id == client.id).count():
        raise HTTPException(409, "Remove this client's campaigns and users first")
    audit(db, user, "client.delete", client.name)
    db.delete(client)
    db.commit()
    return {"deleted": True}


# --------------------------------------------------------------------------- campaigns
@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Campaign)
    if user.role == "client":
        q = q.filter(Campaign.client_id == user.client_id)
    return [campaign_out(c, for_client=user.role == "client") for c in q.order_by(Campaign.created_at.desc()).all()]


@router.post("/campaigns")
def create_campaign(body: CampaignIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    if body.client_id and not db.get(Client, body.client_id):
        raise HTTPException(404, "Client not found")
    campaign = Campaign(**body.model_dump())
    db.add(campaign)
    audit(db, user, "campaign.create", campaign.name)
    db.commit()
    return campaign_out(campaign)


@router.patch("/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignIn, db: Session = Depends(get_db), user: User = Depends(team_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    if body.client_id and not db.get(Client, body.client_id):
        raise HTTPException(404, "Client not found")
    for key, value in body.model_dump().items():
        setattr(campaign, key, value)
    db.commit()
    return campaign_out(campaign)


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(team_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    audit(db, user, "campaign.delete", campaign.name)
    db.delete(campaign)
    db.commit()
    return {"deleted": True}


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    is_client = user.role == "client"
    links = [l for l in campaign.links if l.shortlisted] if is_client else campaign.links
    return {**campaign_out(campaign, for_client=is_client), "links": [link_out(l, for_client=is_client) for l in links]}


@router.post("/campaigns/{campaign_id}/creators")
def add_creators(campaign_id: int, body: AddCreators, db: Session = Depends(get_db), user: User = Depends(team_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    existing = {l.creator_id for l in campaign.links}
    added = 0
    for creator in db.query(Creator).filter(Creator.id.in_(body.creator_ids)).all():
        if creator.id in existing:  # a creator is linked to a campaign only once
            continue
        campaign.links.append(CampaignCreator(creator_id=creator.id, shortlisted=body.shortlisted, added_by=user.id))
        creator.activities.append(Activity(user_id=user.id, user_name=user.name, action="campaign",
                                           detail=f"Added to campaign “{campaign.name}”"))
        added += 1
    db.commit()
    return {"added": added, "already_in_campaign": len(body.creator_ids) - added}


@router.patch("/campaigns/{campaign_id}/creators/{link_id}")
def update_link(campaign_id: int, link_id: int, body: LinkPatch, db: Session = Depends(get_db), user: User = Depends(team_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    link = next((l for l in campaign.links if l.id == link_id), None)
    if not link:
        raise HTTPException(404, "Creator is not in this campaign")
    link.shortlisted = body.shortlisted
    db.commit()
    return link_out(link)


@router.delete("/campaigns/{campaign_id}/creators/{link_id}")
def remove_link(campaign_id: int, link_id: int, db: Session = Depends(get_db), user: User = Depends(team_user)):
    campaign = scoped_campaign(db, campaign_id, user)
    link = next((l for l in campaign.links if l.id == link_id), None)
    if not link:
        raise HTTPException(404, "Creator is not in this campaign")
    campaign.links.remove(link)
    db.commit()
    return {"deleted": True}


@router.post("/campaigns/{campaign_id}/creators/{link_id}/decision")
def decide(campaign_id: int, link_id: int, body: Decision, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Lead approval. Team members can decide on any lead; a client only on leads shortlisted for them."""
    campaign = scoped_campaign(db, campaign_id, user)
    link = next((l for l in campaign.links if l.id == link_id), None)
    if not link or (user.role == "client" and not link.shortlisted):
        raise HTTPException(404, "Creator is not in this campaign")
    link.approval, link.approval_note = body.approval, body.note
    link.decided_by, link.decided_at = user.id, utcnow()
    link.creator.activities.append(Activity(
        user_id=user.id, user_name=user.name, action="approval",
        detail=f"{body.approval.title()} for “{campaign.name}” by {'client' if user.role == 'client' else 'team'}. {body.note}".strip()))
    db.commit()
    return link_out(link, for_client=user.role == "client")
