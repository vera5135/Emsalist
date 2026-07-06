"""P1.5.6 / P1.12 — DB-backed auth routes with contract response models."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.services.auth_service import SecurityContext, resolve_current_user, get_auth_mode, create_access_token, get_security_context, ACCESS_TOKEN_MINUTES
from app.services.auth_manager import auth_manager, require_authenticated
from app.models.auth_contract_models import (
    LoginRequest, LoginResponse, UserInfo,
    TokenRefreshResponse, MeResponse, MessageResponse,
    ChangePasswordRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

SET_COOKIE = 'refresh_token={token}; HttpOnly; Path=/auth; Max-Age=604800; SameSite=Lax'


@router.post("/login", response_model=LoginResponse, operation_id="auth_login")
async def login(body: LoginRequest, response: Response) -> LoginResponse:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        return LoginResponse(
            access_token=create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role),
            token_type="bearer",
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            user=UserInfo(id=ctx.actor_id, tenant=ctx.tenant_id, role=ctx.role),
        )
    try:
        result = await auth_manager.login(
            tenant_slug=body.tenant_slug,
            email=body.email,
            password=body.password,
        )
        user_data = result.get("user", {})
        return LoginResponse(
            access_token=result["access_token"],
            token_type=result.get("token_type", "bearer"),
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            user=UserInfo(
                id=user_data.get("id", ""),
                tenant=user_data.get("tenant", ""),
                role=user_data.get("role", "lawyer"),
            ),
        )
    except HTTPException:
        raise


@router.post("/refresh", response_model=TokenRefreshResponse, operation_id="auth_refresh")
async def refresh(request: Request) -> TokenRefreshResponse:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        return TokenRefreshResponse(
            access_token=create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role),
            token_type="bearer",
        )
    rt = request.cookies.get("refresh_token") or ""
    if not rt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")
    try:
        result = await auth_manager.refresh(rt)
        return TokenRefreshResponse(
            access_token=result["access_token"],
            token_type=result.get("token_type", "bearer"),
        )
    except HTTPException:
        raise


@router.get("/me", response_model=MeResponse, operation_id="auth_me")
async def me(ctx: SecurityContext = Depends(resolve_current_user)) -> MeResponse:
    return MeResponse(
        user_id=ctx.actor_id,
        tenant_id=ctx.tenant_id,
        role=ctx.role,
        authenticated=ctx.authenticated,
        auth_mode=get_auth_mode(),
    )


@router.post("/logout", response_model=MessageResponse, operation_id="auth_logout")
async def logout(ctx: SecurityContext = Depends(resolve_current_user)) -> MessageResponse:
    if get_auth_mode() == "local":
        return MessageResponse(message="Logged out")
    await auth_manager.logout(ctx)
    return MessageResponse(message="Logged out")


@router.post("/logout-all", response_model=MessageResponse, operation_id="auth_logout_all")
async def logout_all(ctx: SecurityContext = Depends(resolve_current_user)) -> MessageResponse:
    if get_auth_mode() == "local":
        return MessageResponse(message="All sessions revoked")
    await auth_manager.logout_all(ctx)
    return MessageResponse(message="All sessions revoked")


@router.post("/change-password", response_model=MessageResponse, operation_id="auth_change_password")
async def change_password(body: ChangePasswordRequest, ctx: SecurityContext = Depends(resolve_current_user)) -> MessageResponse:
    if get_auth_mode() == "local":
        return MessageResponse(message="Not available in local mode")
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)
