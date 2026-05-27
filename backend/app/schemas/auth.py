from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID


class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    refresh_token: str
    user: dict


class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str

    class Config:
        from_attributes = True
