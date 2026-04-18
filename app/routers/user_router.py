from fastapi import APIRouter, Depends
from sqlalchemy import select
from typing import List
from app.backend.dependencies import db_dep, require_role
from app.models.user_model import User, UserRole
from app.schemas.auth_schemas import UserResponse
from app.backend.dependencies import get_current_user
router = APIRouter(prefix="/api/users", tags=["Users"])

@router.get("/inspectors", response_model=List[UserResponse])
async def get_inspectors(db: db_dep, current_user: User = Depends(require_role(UserRole.ADMIN))):
    stmt = select(User).where(User.role == UserRole.INSPECTOR)
    result = await db.execute(stmt)
    return result.scalars().all()







@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user