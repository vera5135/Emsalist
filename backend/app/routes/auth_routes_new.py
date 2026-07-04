"""P1.5 — Auth API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.auth_service import (
    SecurityContext,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_auth_mode,
    get_security_context,
    hash_password,
    resolve_current_user,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
async def login(body: dict) -> dict:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        token = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role)
        return {"access_token": token, "token_type": "bearer", "user": {"id": ctx.actor_id, "tenant": ctx.tenant_id, "role": ctx.role}}

    email = str(body.get("email", "")).strip()
    password = str(body.get("password", "")).strip()
    tenant = str(body.get("tenant_slug", "local")).strip()

    if not email or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email and password required")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


@router.post("/refresh")
async def refresh(body: dict) -> dict:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        token = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role)
        return {"access_token": token, "token_type": "bearer"}

    refresh_token = str(body.get("refresh_token", "")).strip()
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")

    try:
        payload = decode_token(refresh_token, "refresh")
        ctx = get_security_context()
        new_access = create_access_token(payload["sub"], ctx.tenant_id, "lawyer", payload.get("session_id", ""))
        return {"access_token": new_access, "token_type": "bearer"}
    except HTTPException:
        raise


@router.get("/me")
async def me(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    return {
        "user_id": ctx.actor_id,
        "tenant_id": ctx.tenant_id,
        "role": ctx.role,
        "authenticated": ctx.authenticated,
        "auth_mode": get_auth_mode(),
    }


@router.post("/logout")
async def logout(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    return {"message": "Logged out"}


@router.post("/change-password")
async def change_password(body: dict, ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    if get_auth_mode() == "local":
        return {"message": "Password change not available in local mode"}
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Password change requires database")
