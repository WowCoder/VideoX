"""运营后台公共 API 契约。"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=200)
    otp: str = Field(..., min_length=6, max_length=12)


class AdminOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    status: str
    permissions: list[str]
    last_login_at: datetime | None = None


class AdminAuthResponse(BaseModel):
    admin: AdminOut
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminMessageResponse(BaseModel):
    message: str


class ReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)
