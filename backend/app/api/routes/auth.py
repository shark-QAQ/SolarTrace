# app/api/routes/auth.py
"""认证与用户管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import AdminDep, DbDep, UserDep, client_ip
from app.repositories import qa_repo, user_repo
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import auth_service

router = APIRouter(tags=["认证"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbDep, request: Request) -> dict:
    result = auth_service.login(db, payload)
    qa_repo.add_audit(
        db,
        user_id=result["user"]["id"],
        username=result["user"]["username"],
        action="login",
        resource_type="auth",
        resource_id="",
        detail={"method": "password"},
        ip=client_ip(request),
    )
    db.commit()
    return result


@router.get("/auth/me", response_model=UserOut)
def me(user: UserDep) -> dict:
    return user_repo.user_to_dict(user)


@router.post("/auth/password")
def change_password(
    payload: ChangePasswordRequest,
    db: DbDep,
    user: UserDep,
    request: Request,
) -> dict:
    from app.core.errors import ValidationFailed
    from app.core.security import verify_password

    if not verify_password(payload.old_password, user.hashed_password):
        raise ValidationFailed("原密码不正确")
    auth_service.update_user(
        db, user.id, {"password": payload.new_password}, operator_role=user.role, operator_id=user.id
    )
    qa_repo.add_audit(
        db, user.id, user.username, "change_password", "auth", str(user.id), {}, client_ip(request)
    )
    db.commit()
    return {"message": "密码已更新"}


# ---------- 用户管理（管理员） ----------
@router.get("/users")
def list_users(db: DbDep, _: AdminDep, page: int = 1, page_size: int = 20) -> dict:
    return auth_service.list_users(db, page=page, page_size=page_size)


@router.post("/users", response_model=UserOut)
def create_user(payload: UserCreate, db: DbDep, admin: AdminDep, request: Request) -> dict:
    out = auth_service.create_user(db, payload, operator_role=admin.role)
    qa_repo.add_audit(
        db,
        admin.id,
        admin.username,
        "create_user",
        "user",
        str(out["id"]),
        {"username": out["username"], "role": out["role"]},
        client_ip(request),
    )
    db.commit()
    return out


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, payload: UserUpdate, db: DbDep, admin: AdminDep, request: Request
) -> dict:
    fields = payload.model_dump(exclude_none=True)
    out = auth_service.update_user(db, user_id, fields, operator_role=admin.role, operator_id=admin.id)
    qa_repo.add_audit(
        db,
        admin.id,
        admin.username,
        "update_user",
        "user",
        str(user_id),
        {"fields": list(fields)},
        client_ip(request),
    )
    db.commit()
    return out
