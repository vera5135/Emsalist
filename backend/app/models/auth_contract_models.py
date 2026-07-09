"""P1.12 / P2.2B2A — Authentication contract models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant_slug: str | None = Field(default=None)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class UserInfo(BaseModel):
    id: str
    tenant: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = Field(default="bearer")
    expires_in: int = Field(default=1800, description="Seconds until access token expiry")
    refresh_expires_in: int | None = Field(default=None, description="Seconds until refresh token expiry")
    user: UserInfo | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")
    expires_in: int = Field(default=1800, description="Seconds until access token expiry")
    refresh_expires_in: int = Field(default=604800, description="Seconds until refresh token expiry")


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


class AppleLoginRequest(BaseModel):
    authorization_code: str = Field(min_length=1)
    raw_nonce: str = Field(min_length=1)


class AppleAuthenticatedResponse(BaseModel):
    state: Literal["authenticated"] = "authenticated"
    access_token: str
    refresh_token: str | None = None
    token_type: str = Field(default="bearer")
    expires_in: int = Field(default=1800)
    refresh_expires_in: int | None = Field(default=604800)
    user: UserInfo | None = None


class AppleLinkRequiredResponse(BaseModel):
    state: Literal["link_required"] = "link_required"
    link_ticket: str
    link_expires_in: int = Field(default=300)


class AppleLinkRequest(BaseModel):
    link_ticket: str = Field(min_length=1)
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)


class AppleStatusResponse(BaseModel):
    linked: bool
    provider: str


class AppleUnlinkRequest(BaseModel):
    current_password: str = Field(min_length=1)
