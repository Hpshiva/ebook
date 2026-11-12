from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from ..core.config import DEFAULT_SETTINGS
from ..models import AuditLog, Setting, utcnow


def get_settings(db: Session) -> dict:
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for row in db.query(Setting).all():
        if isinstance(merged.get(row.key), dict) and isinstance(row.value, dict):
            merged[row.key].update(row.value)
        else:
            merged[row.key] = row.value
    return merged


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


def update_settings(db: Session, patch: dict) -> dict:
    current = get_settings(db)
    for key, value in patch.items():
        if key not in DEFAULT_SETTINGS:
            continue
        if isinstance(DEFAULT_SETTINGS[key], dict) and isinstance(value, dict):
            value = {**current[key], **value}
        if key == "fx" and value.get("usd_inr") != current["fx"].get("usd_inr"):
            value = {**value, "updated_at": utcnow().isoformat(), "source": "entered manually"}
        set_setting(db, key, value)
    db.commit()
    return get_settings(db)


def audit(db: Session, user, action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=getattr(user, "id", None), user_email=getattr(user, "email", ""),
                    action=action, detail=detail[:2000]))
