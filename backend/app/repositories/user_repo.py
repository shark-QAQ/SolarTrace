# app/repositories/user_repo.py
"""用户仓储。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User


def get_by_username(db: Session, username: str) -> User | None:
    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()


def get(db: Session, user_id: int) -> User | None:
    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()


def list_users(db: Session, page: int = 1, page_size: int = 20) -> tuple[int, list[User]]:
    total = int(db.execute(select(func.count(User.id))).scalar_one())
    rows = db.execute(
        select(User).order_by(User.id).offset((page - 1) * page_size).limit(page_size)
    ).scalars()
    return total, list(rows)


def create(db: Session, *, username: str, hashed_password: str, display_name: str, role: str) -> User:
    u = User(
        username=username,
        hashed_password=hashed_password,
        display_name=display_name,
        role=role,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def update(db: Session, user: User, **fields: Any) -> User:
    for k, v in fields.items():
        if v is not None:
            setattr(user, k, v)
    db.flush()
    return user


def user_to_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "display_name": u.display_name,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat(),
    }
