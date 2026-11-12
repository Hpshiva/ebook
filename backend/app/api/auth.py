from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from ..core.db import get_db
from ..core.security import admin_user, create_token, current_user, hash_password, verify_password
from ..models import Client, User
from ..services.settings_store import audit
from .serializers import user_out

router = APIRouter(prefix="/api", tags=["auth"])
_failures: dict[str, list[float]] = {}
LOCK_AFTER, LOCK_SECONDS = 5, 300


class SetupIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(SetupIn):
    role: str = Field(pattern="^(admin|staff|client)$")
    client_id: int | None = None


class UserPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|staff|client)$")
    client_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


@router.get("/auth/status")
def status(db: Session = Depends(get_db)):
    return {"needs_setup": db.query(User).count() == 0}


@router.post("/auth/setup")
def setup(body: SetupIn, db: Session = Depends(get_db)):
    """First run only: create the administrator account."""
    if db.query(User).count():
        raise HTTPException(409, "Setup is already complete")
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role="admin")
    db.add(user)
    db.flush()
    audit(db, user, "setup", "Administrator account created")
    db.commit()
    return {"token": create_token(user.id), "user": user_out(user)}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    recent = [t for t in _failures.get(email, []) if t > time.time() - LOCK_SECONDS]
    if len(recent) >= LOCK_AFTER:
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        _failures[email] = recent + [time.time()]
        raise HTTPException(401, "Incorrect email or password")
    _failures.pop(email, None)
    return {"token": create_token(user.id), "user": user_out(user)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    return [user_out(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "A user with this email already exists")
    if body.role == "client" and (not body.client_id or not db.get(Client, body.client_id)):
        raise HTTPException(422, "Client users must be linked to a client")
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password),
                role=body.role, client_id=body.client_id if body.role == "client" else None)
    db.add(user)
    audit(db, admin, "user.create", f"{user.email} ({user.role})")
    db.commit()
    return user_out(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("is_active") is False or data.get("role") not in (None, "admin")):
        raise HTTPException(422, "You cannot deactivate or demote your own account")
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for key, value in data.items():
        setattr(user, key, value)
    if user.role != "client":
        user.client_id = None
    elif not user.client_id:
        raise HTTPException(422, "Client users must be linked to a client")
    audit(db, admin, "user.update", f"{user.email}: {', '.join(body.model_dump(exclude_unset=True).keys())}")
    db.commit()
    return user_out(user)
