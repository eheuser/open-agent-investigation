from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    """Schema for creating a new user."""
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    role: int = Field(default=0, ge=0, le=1, description="0=regular, 1=admin")


class UserLogin(BaseModel):
    """Schema for user login."""
    username: str
    password: str


class UserRead(BaseModel):
    """Schema for reading user data (response)."""
    id: int
    username: str
    role: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"


__all__ = ["UserCreate", "UserLogin", "UserRead", "TokenResponse"]
