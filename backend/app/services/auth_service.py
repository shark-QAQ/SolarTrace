# app/services/auth_service.py
"""认证与用户管理业务。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AuthError, ConflictError, NotFoundError, PermissionDenied
from app.core.security import create_access_token, hash_password, verify_password
from app.models.enums import Role
from app.repositories import user_repo
from app.schemas.auth import LoginRequest, UserCreate


def login(db: Session, payload: LoginRequest) -> dict:
    user = user_repo.get_by_username(db, payload.username.strip())
    if not user or not verify_password(payload.password, user.hashed_password):
        raise AuthError("用户名或密码错误")
    if not user.is_active:
        raise PermissionDenied("账号已被停用")
    token, expires_in = create_access_token(str(user.id), extra={"role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": user_repo.user_to_dict(user),
    }


def create_user(db: Session, payload: UserCreate, operator_role: str) -> dict:
    if Role(operator_role).level < Role.ADMIN.level:
        raise PermissionDenied("仅管理员可创建用户")
    if user_repo.get_by_username(db, payload.username.strip()):
        raise ConflictError(f"用户名 {payload.username} 已存在")
    user = user_repo.create(
        db,
        username=payload.username.strip(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        role=payload.role,
    )
    db.commit()
    return user_repo.user_to_dict(user)


def list_users(db: Session, page: int, page_size: int) -> dict:
    total, users = user_repo.list_users(db, page=page, page_size=page_size)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [user_repo.user_to_dict(u) for u in users],
    }


def update_user(db: Session, user_id: int, fields: dict, operator_role: str, operator_id: int) -> dict:
    user = user_repo.get(db, user_id)
    if not user:
        raise NotFoundError("用户不存在")
    is_self = user.id == operator_id
    if not is_self and Role(operator_role).level < Role.ADMIN.level:
        raise PermissionDenied("仅管理员可修改他人账号")
    data: dict = {}
    if fields.get("password"):
        data["hashed_password"] = hash_password(fields["password"])
    for key in ("display_name", "role", "is_active"):
        if key in fields and fields[key] is not None:
            if key == "role" and not is_self and Role(operator_role).level < Role.ADMIN.level:
                raise PermissionDenied("仅管理员可调整角色")
            data[key] = fields[key]
    user_repo.update(db, user, **data)
    db.commit()
    return user_repo.user_to_dict(user)
