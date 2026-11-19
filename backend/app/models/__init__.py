"""Database models. A creator is stored once globally; its relationship to each
client campaign lives in CampaignCreator, which is what tenant isolation keys on."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


CRM_STATUSES = [
    "New", "Needs Review", "Qualified", "Not Qualified", "Contacted", "Follow-up",
    "Replied", "Interested", "Negotiating", "Partnered", "Rejected", "Closed",
]
SELLING_STATUSES = ["SELLING", "CHECK", "NOT_SELLING", "UNKNOWN"]


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="staff")
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="Active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="client")


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    # client_id NULL = our own partnership campaign (business model A).
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    niche: Mapped[str] = mapped_column(String(80), default="")
    product_name: Mapped[str] = mapped_column(String(160), default="")
    target_leads: Mapped[int] = mapped_column(Integer, default=0)
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="Active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    client: Mapped[Client | None] = relationship(back_populates="campaigns")
    links: Mapped[list["CampaignCreator"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Creator(Base):
    __tablename__ = "creators"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), default="")
    profile_url: Mapped[str] = mapped_column(String(255), default="")
    biography: Mapped[str] = mapped_column(Text, default="")
    followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    following: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posts_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_pic_url: Mapped[str] = mapped_column(Text, default="")
    external_urls: Mapped[list] = mapped_column(JSON, default=list)
    business_category: Mapped[str] = mapped_column(String(160), default="")
    is_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_private: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    country: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(60), default="")
    niche: Mapped[str] = mapped_column(String(80), default="", index=True)
    sub_niche: Mapped[str] = mapped_column(String(80), default="")
    captions: Mapped[list] = mapped_column(JSON, default=list)
    related_usernames: Mapped[list] = mapped_column(JSON, default=list)

    reel_views: Mapped[list] = mapped_column(JSON, default=list)
    reels_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    median_reel_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    selling_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    selling_reasons: Mapped[list] = mapped_column(JSON, default=list)
    selling_override: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    lead_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[str] = mapped_column(String(10), default="Low")
    verdict: Mapped[str] = mapped_column(String(20), default="needs_review", index=True)
    verdict_reasons: Mapped[list] = mapped_column(JSON, default=list)

    crm_status: Mapped[str] = mapped_column(String(30), default="New", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Retired: demo data was removed. Kept only so old rows can be found and cleaned up.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(40), default="")
    data_provider: Mapped[str] = mapped_column(String(40), default="")
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reels_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    contacts: Mapped[list["CreatorContact"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    snapshots: Mapped[list["CreatorSnapshot"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="creator", cascade="all, delete-orphan", order_by="Activity.created_at.desc()"
    )
    links: Mapped[list["CampaignCreator"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    outreach: Mapped[list["OutreachMessage"]] = relationship(back_populates="creator", cascade="all, delete-orphan")
    partnerships: Mapped[list["Partnership"]] = relationship(back_populates="creator", cascade="all, delete-orphan")

    @property
    def effective_selling_status(self) -> str:
        return (self.selling_override or {}).get("status") or self.selling_status


class CreatorContact(Base):
    __tablename__ = "creator_contacts"
    __table_args__ = (UniqueConstraint("creator_id", "type", "value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # email | phone | contact_page
    value: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(60), default="")
    source_url: Mapped[str] = mapped_column(String(255), default="")
    validation_status: Mapped[str] = mapped_column(String(30), default="unverified")
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    creator: Mapped[Creator] = relationship(back_populates="contacts")


class CreatorSnapshot(Base):
    """History of each collection, so follower/view changes can be analysed over time."""
    __tablename__ = "creator_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    provider: Mapped[str] = mapped_column(String(40), default="")
    followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    median_reel_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    creator: Mapped[Creator] = relationship(back_populates="snapshots")


class CampaignCreator(Base):
    __tablename__ = "campaign_creators"
    __table_args__ = (UniqueConstraint("campaign_id", "creator_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    # Shortlisted = visible to the client. Client then approves or rejects.
    shortlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    approval: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    approval_note: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    campaign: Mapped[Campaign] = relationship(back_populates="links")
    creator: Mapped[Creator] = relationship(back_populates="links")


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_name: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    creator: Mapped[Creator] = relationship(back_populates="activities")


class SearchRun(Base):
    __tablename__ = "search_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, index=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    discovery_source: Mapped[str] = mapped_column(String(40), default="")
    profile_provider: Mapped[str] = mapped_column(String(40), default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    requested: Mapped[int] = mapped_column(Integer, default=0)
    collected: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    qualified: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    actor_runs: Mapped[int] = mapped_column(Integer, default=0)
    est_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    results: Mapped[list["SearchResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class SearchResult(Base):
    __tablename__ = "search_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    run: Mapped[SearchRun] = relationship(back_populates="results")
    creator: Mapped[Creator] = relationship()


class OutreachTemplate(Base):
    __tablename__ = "outreach_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text)
    channel: Mapped[str] = mapped_column(String(20), default="email")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|contacted|replied|no_reply
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    creator: Mapped[Creator] = relationship(back_populates="outreach")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    price: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Partnership(Base):
    __tablename__ = "partnerships"
    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    commission_pct: Mapped[float] = mapped_column(Float, default=0)
    fixed_payment: Mapped[float] = mapped_column(Float, default=0)
    tracking_url: Mapped[str] = mapped_column(String(255), default="")
    promo_code: Mapped[str] = mapped_column(String(60), default="")
    clicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conversions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue: Mapped[float] = mapped_column(Float, default=0)
    amount_paid: Mapped[float] = mapped_column(Float, default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    creator: Mapped[Creator] = relationship(back_populates="partnerships")
    product: Mapped[Product] = relationship()


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
