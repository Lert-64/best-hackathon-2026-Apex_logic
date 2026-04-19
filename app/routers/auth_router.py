from fastapi import APIRouter, Body, Form, HTTPException, status, Response
from sqlalchemy import select
from app.backend.dependencies import db_dep
from app.schemas.auth_schemas import LoginRequest, TokenResponse, RefreshTokenRequest
from app.models.user_model import User, UserRole
from app.backend.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    db: db_dep,
    response: Response,
    credentials: LoginRequest | None = Body(default=None),
    username: str | None = Form(default=None),
    password: str | None = Form(default=None),
):
    resolved_username = credentials.username if credentials else username
    resolved_password = credentials.password if credentials else password

    if not resolved_username or not resolved_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="username and password are required",
        )

    stmt = select(User).filter(User.username == resolved_username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(resolved_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

    target_url = "/login"
    if user.role == UserRole.ADMIN:
        target_url = "/admin"
    elif user.role == UserRole.INSPECTOR:
        target_url = "/inspector"
    elif user.role == UserRole.VOLUNTEER:
        target_url = "/volunteer"

    response.headers["HX-Redirect"] = target_url
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        path="/",
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def get_refresh_token(req: RefreshTokenRequest, db: db_dep):
    payload = decode_token(req.refresh_token, is_refresh=True)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    stmt = select(User).filter(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    new_access_token = create_access_token(data={"sub": user.username})
    new_refresh_token = create_refresh_token(data={"sub": user.username})

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.headers["HX-Redirect"] = "/login"
    return {"message": "Successfully logged out"}


