# app/api/deps.py
"""FastAPI 公共依赖：会话、运行时、当前用户、角色门禁、客户端 IP。"""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AuthError, PermissionDenied
from app.core.security import decode_token
from app.models import User
from app.models.enums import Role
from app.providers.registry import RagRuntime, get_runtime
from app.repositories import user_repo

bearer = HTTPBearer(auto_error=False)

DbDep = Annotated[Session, Depends(get_db)]
RuntimeDep = Annotated[RagRuntime, Depends(get_runtime)]


def get_current_user(
    db: DbDep,
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if cred is None:
        raise AuthError("缺少认证信息，请先登录")
    payload = decode_token(cred.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthError("登录态无效") from exc
    user = user_repo.get(db, user_id)
    if not user or not user.is_active:
        raise AuthError("账号不存在或已停用")
    return user


def require_roles(*roles: str) -> Callable:
    """按最小权限门槛放行：传 'viewer'/'editor'/'admin'，管理员自动包含低阶能力。"""
    min_level = min(Role(r).level for r in roles)

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if Role(user.role).level < min_level:
            raise PermissionDenied("当前账号无权限执行该操作")
        return user

    return dependency


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.client.host if request.client else "unknown")


UserDep = Annotated[User, Depends(get_current_user)]
EditorDep = Annotated[User, Depends(require_roles(Role.EDITOR.value, Role.ADMIN.value))]
AdminDep = Annotated[User, Depends(require_roles(Role.ADMIN.value))]
