"""P1.12 — Authentication contract models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant_slug: str = Field(default="local", min_length=1)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class UserInfo(BaseModel):
    id: str
    tenant: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")
    expires_in: int = Field(default=1800, description="Seconds until token expiry")
    user: UserInfo | None = None


class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")


class MeResponse(BaseModel):
    user_id: str
    tenant_id: str
    role: str
    authenticated: bool
    auth_mode: str


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
