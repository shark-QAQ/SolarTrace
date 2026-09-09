# app/schemas/auth.py
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.models.enums import Role


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(min_length=6, max_length=128)
    display_name: str = Field(default="", max_length=64)
    role: str = Role.VIEWER.value

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        if v not in {r.value for r in Role}:
            raise ValueError(f"role 必须为 {[r.value for r in Role]}")
        return v


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str | None) -> str | None:
        if v is not None and v not in {r.value for r in Role}:
            raise ValueError(f"role 必须为 {[r.value for r in Role]}")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


TokenResponse.model_rebuild()
