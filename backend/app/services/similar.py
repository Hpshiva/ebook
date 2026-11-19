"""Similar creators from our own database, with the reasons shown. Nothing is invented."""
from __future__ import annotations

import math
import re

from sqlalchemy.orm import Session

from ..models import Creator

STOP = {"the", "and", "for", "with", "your", "you", "from", "that", "this", "new", "every", "about", "tips"}


def _words(c: Creator) -> set[str]:
    text = f"{c.biography} {c.business_category} {' '.join(c.captions or [])}".lower()
    return {w for w in re.findall(r"[a-z]{4,}", text) if w not in STOP}


def _close(a: int | None, b: int | None) -> float | None:
    if not a or not b:
        return None
    return max(0.0, 1 - abs(math.log10(a) - math.log10(b)))  # 1 = same size, 0 = 10x apart


def find_similar(db: Session, target: Creator, limit: int = 10) -> list[dict]:
    words = _words(target)
    out = []
    q = db.query(Creator).filter(Creator.id != target.id,
                                 Creator.last_collected_at.isnot(None))
    for c in q.limit(2000):
        score, reasons = 0.0, []
        if target.niche and c.niche == target.niche:
            score += 30
            reasons.append(f"Same niche ({c.niche})")
        shared = words & _words(c)
        if words and shared:
            ratio = len(shared) / len(words | _words(c))
            score += 25 * min(1, ratio * 3)
            reasons.append("Shared keywords: " + ", ".join(sorted(shared)[:5]))
        f = _close(target.followers, c.followers)
        if f and f > 0.6:
            score += 15 * f
            reasons.append(f"Similar audience size ({c.followers:,} followers)")
        v = _close(target.median_reel_views, c.median_reel_views)
        if v and v > 0.6:
            score += 10 * v
            reasons.append(f"Similar reel views ({c.median_reel_views:,} median)")
        if target.country and c.country == target.country:
            score += 8
            reasons.append(f"Same country ({c.country})")
        if target.language and c.language == target.language:
            score += 5
            reasons.append(f"Same language ({c.language})")
        if target.business_category and c.business_category == target.business_category:
            score += 7
            reasons.append(f"Same category ({c.business_category})")
        if c.username in (target.related_usernames or []):
            score += 10
            reasons.append("Listed by the data provider as a related account")
        if score >= 30:
            out.append({"creator_id": c.id, "similarity": round(score, 1), "reasons": reasons})
    out.sort(key=lambda r: r["similarity"], reverse=True)
    return out[:limit]
