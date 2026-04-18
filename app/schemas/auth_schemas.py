from pydantic import BaseModel
from uuid import UUID
from app.models.enums import UserRole

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    role: UserRole