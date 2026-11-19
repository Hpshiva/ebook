from __future__ import annotations

import io

import pandas as pd

from ..models import Creator

COLUMNS = [
    "Username", "Full name", "Instagram URL", "Country", "Language", "Niche", "Followers",
    "Following", "Median Reel views", "Reels analyzed", "Engagement rate (%)", "Selling status",
    "Selling reason", "Business email", "Contact source", "Contact validation", "Lead score",
    "Score breakdown", "Confidence", "Last analyzed", "Campaign", "CRM status", "Notes",
]


def creator_row(c: Creator, campaign: str = "", notes: str | None = None) -> dict:
    emails = [x for x in c.contacts if x.type == "email"]
    breakdown = "; ".join(
        f"{k}: {'n/a' if v.get('points') is None else v['points']}/{v['weight']}"
        for k, v in (c.score_breakdown or {}).items()
    )
    if notes is None:
        notes = " | ".join(a.detail for a in c.activities if a.action == "note")
    return {
        "Username": c.username,
        "Full name": c.full_name,
        "Instagram URL": c.profile_url,
        "Country": c.country,
        "Language": c.language,
        "Niche": c.niche,
        "Followers": c.followers,
        "Following": c.following,
        "Median Reel views": c.median_reel_views,
        "Reels analyzed": c.reels_analyzed,
        "Engagement rate (%)": c.engagement_rate,
        "Selling status": c.effective_selling_status,
        "Selling reason": " ".join(c.selling_reasons or [])
        + (f" [Manual override by {c.selling_override.get('by')}]" if c.selling_override else ""),
        "Business email": ", ".join(x.value for x in emails),
        "Contact source": ", ".join(dict.fromkeys(x.source for x in emails)),
        "Contact validation": ", ".join(dict.fromkeys(x.validation_status for x in emails)),
        "Lead score": c.lead_score,
        "Score breakdown": breakdown,
        "Confidence": c.confidence,
        "Last analyzed": c.last_collected_at.strftime("%Y-%m-%d %H:%M") if c.last_collected_at else "",
        "Campaign": campaign,
        "CRM status": c.crm_status,
        "Notes": notes,
    }


def _safe(value):
    """Stop spreadsheet formula injection from scraped text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def build_export(rows: list[dict], fmt: str) -> tuple[bytes, str, str]:
    df = pd.DataFrame([{k: _safe(v) for k, v in r.items()} for r in rows], columns=COLUMNS)
    for col in ("Followers", "Following", "Median Reel views", "Reels analyzed"):
        df[col] = df[col].astype("Int64")  # whole numbers even when some rows are empty
    if fmt == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Creators")
            sheet = writer.sheets["Creators"]
            for i, col in enumerate(COLUMNS, start=1):
                width = min(45, max(12, len(col) + 2))
                sheet.column_dimensions[sheet.cell(row=1, column=i).column_letter].width = width
            sheet.freeze_panes = "A2"
        return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    return df.to_csv(index=False).encode("utf-8-sig"), "text/csv", "csv"
