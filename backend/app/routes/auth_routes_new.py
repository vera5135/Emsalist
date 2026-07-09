"""P1.5.6 / P1.12 — DB-backed auth routes with contract response models."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from app.services.auth_service import (
    SecurityContext, resolve_current_user, get_auth_mode, create_access_token,
    get_security_context, ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS,
    check_login_rate, reset_login_rate,
)
from app.services.auth_manager import auth_manager, require_authenticated
from app.models.auth_contract_models import (
    LoginRequest, LoginResponse, UserInfo,
    RefreshRequest, TokenRefreshResponse, MeResponse, MessageResponse,
    ChangePasswordRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_TOKEN_SECONDS = REFRESH_TOKEN_DAYS * 86400


@router.post("/login", response_model=LoginResponse, operation_id="auth_login")
async def login(body: LoginRequest) -> LoginResponse:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        at = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role)
        rt = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role, token_type_value="refresh")
        return LoginResponse(
            access_token=at,
            refresh_token=rt,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            refresh_expires_in=REFRESH_TOKEN_SECONDS,
            user=UserInfo(id=ctx.actor_id, tenant=ctx.tenant_id, role=ctx.role),
        )
    # In-memory rate limit check (per tenant+email)
    rate_key = f"login:{body.tenant_slug}:{body.email.strip().casefold()}"
    limited, retry_after = check_login_rate(rate_key)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait before retrying.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        result = await auth_manager.login(
            tenant_slug=body.tenant_slug,
            email=body.email,
            password=body.password,
        )
        reset_login_rate(rate_key)
        user_data = result.get("user", {})
        return LoginResponse(
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            token_type=result.get("token_type", "bearer"),
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            refresh_expires_in=REFRESH_TOKEN_SECONDS,
            user=UserInfo(
                id=user_data.get("id", ""),
                tenant=user_data.get("tenant", ""),
                role=user_data.get("role", "lawyer"),
            ),
        )
    except HTTPException:
        raise


@router.post("/refresh", response_model=TokenRefreshResponse, operation_id="auth_refresh")
async def refresh(body: RefreshRequest | None = None, request: Request | None = None) -> TokenRefreshResponse:
    if get_auth_mode() == "local":
        ctx = get_security_context()
        at = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role)
        rt = create_access_token(ctx.actor_id, ctx.tenant_id, ctx.role, token_type_value="refresh")
        return TokenRefreshResponse(
            access_token=at,
            refresh_token=rt,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            refresh_expires_in=REFRESH_TOKEN_SECONDS,
        )

    rt_body = body.refresh_token if body and body.refresh_token else ""
    rt_cookie = request.cookies.get("refresh_token", "") if request else ""
    rt_final = ""

    if rt_body and rt_cookie:
        if rt_body != rt_cookie:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conflicting refresh tokens in body and cookie",
            )
        rt_final = rt_body
    elif rt_body:
        rt_final = rt_body
    elif rt_cookie:
        rt_final = rt_cookie
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required",
        )

    try:
        result = await auth_manager.refresh(rt_final)
        return TokenRefreshResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result.get("token_type", "bearer"),
            expires_in=ACCESS_TOKEN_MINUTES * 60,
            refresh_expires_in=REFRESH_TOKEN_SECONDS,
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
async def change_password(
    body: ChangePasswordRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
) -> MessageResponse:
    if get_auth_mode() == "local":
        return MessageResponse(message="Not available in local mode")
    await auth_manager.change_password(ctx, body.current_password, body.new_password)
    return MessageResponse(message="Password changed successfully. All sessions have been revoked; please log in again.")
