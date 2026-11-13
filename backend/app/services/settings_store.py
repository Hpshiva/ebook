from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from ..core.config import DEFAULT_SETTINGS, config
from ..models import AuditLog, Setting, utcnow


def get_settings(db: Session) -> dict:
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for row in db.query(Setting).all():
        if row.key.startswith("_"):  # internal rows (for example the signing key) are never exposed
            continue
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


APIFY_TOKEN_ROW = "_apify_token"  # internal row: never returned by the settings API


def ensure_apify_token(db: Session) -> None:
    """Make config.apify_token reflect the token saved in the app, when the
    environment does not provide one. Called at the start of requests that need it,
    because each server instance has its own memory."""
    if config.apify_token_from_env:
        return
    row = db.get(Setting, APIFY_TOKEN_ROW)
    if row and row.value:
        config.apify_token, config.apify_token_from_app = str(row.value), True
    elif config.apify_token_from_app:  # it was removed in the app
        config.apify_token, config.apify_token_from_app = "", False


def apify_token_source() -> str | None:
    if config.apify_token_from_env:
        return "server environment"
    if config.apify_token_from_app:
        return "saved in the app"
    return "server environment" if config.apify_token else None
