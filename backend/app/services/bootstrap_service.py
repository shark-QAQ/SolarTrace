# app/services/bootstrap_service.py
"""启动自举：初始管理员。"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import User
from app.models.enums import Role

logger = logging.getLogger(__name__)


def ensure_admin(db: Session) -> None:
    settings = get_settings()
    total = int(db.execute(select(func.count(User.id))).scalar_one())
    if total > 0:
        return
    db.add(
        User(
            username=settings.bootstrap_admin_username,
            hashed_password=hash_password(settings.bootstrap_admin_password),
            display_name=settings.bootstrap_admin_display,
            role=Role.ADMIN.value,
            is_active=True,
        )
    )
    db.commit()
    logger.info(
        "已创建初始管理员 %s（生产环境请立即修改密码）", settings.bootstrap_admin_username
    )
