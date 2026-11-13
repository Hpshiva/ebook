"""Password hashing (stdlib PBKDF2), JWT sessions and role checks."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import config
from .db import get_db

ROLES = ("admin", "staff", "client")
_ITER = 240_000
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()
    return f"pbkdf2_sha256${_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(check, digest)
    except (ValueError, AttributeError):
        return False


_SECRET_ROW = "_secret_key"  # settings rows starting with "_" are internal and never returned by the API
_cached_secret: str | None = None


def signing_key(db: Session) -> str:
    """The key that signs login sessions: SECRET_KEY from the environment if set,
    otherwise one generated on first use and kept in the database, so it survives
    restarts and is shared by every server instance."""
    global _cached_secret
    if config.secret_key:
        return config.secret_key
    if _cached_secret:
        return _cached_secret
    from sqlalchemy.exc import IntegrityError

    from ..models import Setting

    row = db.get(Setting, _SECRET_ROW)
    if not row:
        try:
            db.add(Setting(key=_SECRET_ROW, value=secrets.token_urlsafe(48)))
            db.commit()
        except IntegrityError:  # another instance created it at the same moment
            db.rollback()
        row = db.get(Setting, _SECRET_ROW)
    _cached_secret = str(row.value)
    return _cached_secret


def create_token(user_id: int, db: Session) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, signing_key(db), algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
):
    from ..models import User

    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, signing_key(db), algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please sign in again")
    return user


def require_roles(*roles: str):
    def dep(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this")
        return user

    return dep


# Internal team (everything except client-portal users).
team_user = require_roles("admin", "staff")
admin_user = require_roles("admin")
