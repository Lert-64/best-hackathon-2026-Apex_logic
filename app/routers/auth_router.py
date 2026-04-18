from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from app.backend.dependencies import db_dep, get_current_user
from app.schemas.auth_schemas import LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse
from app.models.user_model import User
from app.backend.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: db_dep):
    stmt = select(User).filter(User.username == credentials.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})

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
async def logout():
    return {"message": "Successfully logged out"}


