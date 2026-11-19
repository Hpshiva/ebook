from __future__ import annotations

from ..models import Campaign, CampaignCreator, Client, Creator, OutreachMessage, Partnership, SearchRun, User


def iso(value):
    return value.isoformat() if value else None


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "client_id": u.client_id, "is_active": u.is_active}


def contact_out(x) -> dict:
    return {"id": x.id, "type": x.type, "value": x.value, "source": x.source, "source_url": x.source_url,
            "validation_status": x.validation_status, "discovered_at": iso(x.discovered_at)}


def creator_out(c: Creator, detail: bool = False) -> dict:
    emails = [x.value for x in c.contacts if x.type == "email"]
    out = {
        "id": c.id, "username": c.username, "full_name": c.full_name, "profile_url": c.profile_url,
        "profile_pic_url": c.profile_pic_url, "followers": c.followers, "median_reel_views": c.median_reel_views,
        "reels_analyzed": c.reels_analyzed, "engagement_rate": c.engagement_rate, "niche": c.niche,
        "country": c.country, "language": c.language, "business_category": c.business_category,
        "selling_status": c.effective_selling_status, "selling_overridden": bool(c.selling_override),
        "has_email": bool(emails), "email": emails[0] if emails else None,
        "lead_score": c.lead_score, "confidence": c.confidence, "verdict": c.verdict,
        "verdict_reasons": c.verdict_reasons, "crm_status": c.crm_status, "tags": c.tags or [],
        "owner_id": c.owner_id, "follow_up_date": iso(c.follow_up_date),
        "source": c.source, "collected": c.last_collected_at is not None,
        "last_collected_at": iso(c.last_collected_at), "created_at": iso(c.created_at),
    }
    if detail:
        out.update({
            "biography": c.biography, "following": c.following, "posts_count": c.posts_count,
            "external_urls": c.external_urls or [], "is_verified": c.is_verified, "is_private": c.is_private,
            "sub_niche": c.sub_niche, "reel_views": c.reel_views or [], "data_provider": c.data_provider,
            "selling_detected": c.selling_status, "selling_reasons": c.selling_reasons or [],
            "selling_override": c.selling_override, "score_breakdown": c.score_breakdown or {},
            "contacts": [contact_out(x) for x in c.contacts],
            "related_usernames": c.related_usernames or [],
            "activities": [{"id": a.id, "action": a.action, "detail": a.detail, "user_name": a.user_name,
                            "created_at": iso(a.created_at)} for a in c.activities[:100]],
            "history": [{"collected_at": iso(s.collected_at), "followers": s.followers,
                         "median_reel_views": s.median_reel_views, "engagement_rate": s.engagement_rate}
                        for s in c.snapshots],
            "campaigns": [{"campaign_id": l.campaign_id, "name": l.campaign.name, "shortlisted": l.shortlisted,
                           "approval": l.approval} for l in c.links],
        })
    return out


def client_out(c: Client) -> dict:
    return {"id": c.id, "name": c.name, "contact_name": c.contact_name, "email": c.email, "notes": c.notes,
            "status": c.status, "campaigns": len(c.campaigns), "created_at": iso(c.created_at)}


def campaign_out(c: Campaign, for_client: bool = False) -> dict:
    links = [l for l in c.links if l.shortlisted] if for_client else c.links
    return {
        "id": c.id, "name": c.name, "niche": c.niche, "product_name": c.product_name, "status": c.status,
        "client_id": c.client_id, "client_name": c.client.name if c.client else None,
        "type": "client" if c.client_id else "own", "target_leads": c.target_leads,
        "requirements": c.requirements or {}, "created_at": iso(c.created_at),
        "creators": len(links), "shortlisted": sum(1 for l in links if l.shortlisted),
        "approved": sum(1 for l in links if l.approval == "approved"),
        "rejected": sum(1 for l in links if l.approval == "rejected"),
    }


def link_out(l: CampaignCreator, for_client: bool = False) -> dict:
    c = l.creator
    if for_client:  # clients see the lead sheet, not our internal CRM fields
        emails = [x.value for x in c.contacts if x.type == "email"]
        creator = {"id": c.id, "username": c.username, "full_name": c.full_name, "profile_url": c.profile_url,
                   "followers": c.followers, "median_reel_views": c.median_reel_views, "niche": c.niche,
                   "country": c.country, "selling_status": c.effective_selling_status, "lead_score": c.lead_score,
                   "confidence": c.confidence, "email": emails[0] if emails else None}
    else:
        creator = creator_out(c)
    return {"id": l.id, "campaign_id": l.campaign_id, "shortlisted": l.shortlisted, "approval": l.approval,
            "approval_note": l.approval_note, "decided_at": iso(l.decided_at), "creator": creator}


def run_out(r: SearchRun, with_results: bool = False) -> dict:
    out = {
        "id": r.id, "created_at": iso(r.created_at), "campaign_id": r.campaign_id, "params": r.params,
        "discovery_source": r.discovery_source, "profile_provider": r.profile_provider,
        "discovered": r.discovered, "requested": r.requested, "collected": r.collected, "cached": r.cached,
        "failed": r.failed, "qualified": r.qualified, "needs_review": r.needs_review, "rejected": r.rejected,
        "actor_runs": r.actor_runs, "est_cost_usd": r.est_cost_usd, "actual_cost_usd": r.actual_cost_usd,
        "messages": r.messages or [],
    }
    if with_results:
        out["results"] = [{**creator_out(x.creator), "verdict": x.verdict, "verdict_reasons": x.reasons,
                           "from_cache": x.from_cache} for x in r.results]
    return out


def message_out(m: OutreachMessage) -> dict:
    return {"id": m.id, "creator_id": m.creator_id, "username": m.creator.username,
            "campaign_id": m.campaign_id, "subject": m.subject, "body": m.body, "channel": m.channel,
            "status": m.status, "contacted_at": iso(m.contacted_at), "follow_up_date": iso(m.follow_up_date),
            "notes": m.notes, "created_at": iso(m.created_at),
            "email": next((x.value for x in m.creator.contacts if x.type == "email"), None)}


def partnership_out(p: Partnership) -> dict:
    commission = round(p.revenue * p.commission_pct / 100 + p.fixed_payment, 2)
    return {
        "id": p.id, "creator_id": p.creator_id, "username": p.creator.username,
        "product_id": p.product_id, "product_name": p.product.name, "start_date": iso(p.start_date),
        "commission_pct": p.commission_pct, "fixed_payment": p.fixed_payment, "tracking_url": p.tracking_url,
        "promo_code": p.promo_code, "clicks": p.clicks, "conversions": p.conversions, "revenue": p.revenue,
        "commission_total": commission, "amount_paid": p.amount_paid,
        "commission_owed": round(max(0.0, commission - p.amount_paid), 2),
        "net_revenue": round(p.revenue - commission, 2), "payment_status": p.payment_status, "notes": p.notes,
    }
