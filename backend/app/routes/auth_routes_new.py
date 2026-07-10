"""P1.5.6 / P2.2B2A — DB-backed auth routes with Apple Sign-In endpoints."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from app.config import get_settings
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
    AppleLoginRequest, AppleAuthenticatedResponse, AppleLinkRequiredResponse,
    AppleLinkRequest, AppleStatusResponse, AppleUnlinkRequest,
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
    rate_key = f"login:{body.tenant_slug or ''}:{body.email.strip().casefold()}"
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
async def refresh(body: RefreshRequest) -> TokenRefreshResponse:
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

    try:
        result = await auth_manager.refresh(body.refresh_token)
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


# ---------------------------------------------------------------------------
# Apple Sign-In endpoints
# ---------------------------------------------------------------------------
apple_router = APIRouter(prefix="/auth/apple", tags=["Apple Authentication"])


@apple_router.post("/login", response_model=AppleAuthenticatedResponse | AppleLinkRequiredResponse, operation_id="apple_login")
async def apple_login(body: AppleLoginRequest) -> dict:
    settings = get_settings()
    if get_auth_mode() == "local":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In not available in local mode")

    if not settings.apple_sign_in_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In is currently unavailable")

    rate_key = f"apple_login:{hash(body.authorization_code) % 1000000}"
    limited, retry_after = check_login_rate(rate_key)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait before retrying.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = await auth_manager.apple_login(body.authorization_code, body.raw_nonce)
        reset_login_rate(rate_key)
        if result.get("state") == "link_required":
            return AppleLinkRequiredResponse(
                state="link_required",
                link_ticket=result["link_ticket"],
                link_expires_in=result["link_expires_in"],
            ).model_dump()

        user_data = result.get("user", {})
        return AppleAuthenticatedResponse(
            state="authenticated",
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
        ).model_dump()
    except HTTPException:
        raise


@apple_router.post("/link", response_model=LoginResponse, operation_id="apple_link")
async def apple_link(body: AppleLinkRequest) -> LoginResponse:
    settings = get_settings()
    if get_auth_mode() == "local":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In not available in local mode")

    if not settings.apple_sign_in_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In is currently unavailable")

    rate_key = f"apple_link:{hash(body.email.strip().casefold()) % 1000000}"
    limited, retry_after = check_login_rate(rate_key)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait before retrying.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = await auth_manager.apple_link(body.link_ticket, body.email, body.password)
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


@apple_router.get("/status", response_model=AppleStatusResponse, operation_id="apple_status")
async def apple_status(ctx: SecurityContext = Depends(resolve_current_user)) -> AppleStatusResponse:
    if get_auth_mode() == "local":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In not available in local mode")
    result = await auth_manager.apple_status(ctx)
    return AppleStatusResponse(**result)


@apple_router.post("/unlink", response_model=MessageResponse, operation_id="apple_unlink")
async def apple_unlink(
    body: AppleUnlinkRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
) -> MessageResponse:
    if get_auth_mode() == "local":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Apple Sign-In not available in local mode")
    result = await auth_manager.apple_unlink(ctx, body.current_password)
    return MessageResponse(**result)