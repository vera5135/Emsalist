"""P1.5.6 — DB-backed auth routes."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.services.auth_service import SecurityContext, resolve_current_user, get_auth_mode, create_access_token, get_security_context
from app.services.auth_manager import auth_manager, require_authenticated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

SET_COOKIE = 'refresh_token={token}; HttpOnly; Path=/auth; Max-Age=604800; SameSite=Lax'

@router.post("/login")
async def login(body: dict) -> dict:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        return {"access_token": create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role), "token_type": "bearer",
                "user": {"id": ctx.actor_id, "tenant": ctx.tenant_id, "role": ctx.role}}
    try:
        result = await auth_manager.login(
            tenant_slug=str(body.get("tenant_slug", "local")).strip(),
            email=str(body.get("email", "")).strip(),
            password=str(body.get("password", "")).strip(),
        )
        return result
    except HTTPException: raise

@router.post("/refresh")
async def refresh(request: Request) -> dict:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        return {"access_token": create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role), "token_type": "bearer"}
    rt = request.cookies.get("refresh_token") or ""
    if not rt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")
    try:
        return await auth_manager.refresh(rt)
    except HTTPException: raise

@router.get("/me")
async def me(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    return {"user_id": ctx.actor_id, "tenant_id": ctx.tenant_id, "role": ctx.role, "authenticated": ctx.authenticated, "auth_mode": get_auth_mode()}

@router.post("/logout")
async def logout(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    if get_auth_mode() == "local": return {"message": "Logged out"}
    await auth_manager.logout(ctx)
    return {"message": "Logged out"}

@router.post("/logout-all")
async def logout_all(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    if get_auth_mode() == "local": return {"message": "All sessions revoked"}
    await auth_manager.logout_all(ctx)
    return {"message": "All sessions revoked"}

@router.post("/change-password")
async def change_password(body: dict, ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    if get_auth_mode() == "local": return {"message": "Not available in local mode"}
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
