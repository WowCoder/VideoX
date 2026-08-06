"""用户与鉴权 Schema。"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ── 请求 ──
class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserSettingsUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    notify_asset_processing: bool
    notify_script_generation: bool
    notify_marketing: bool


class PhoneCodeRequest(BaseModel):
    """发送手机验证码请求。"""
    phone: str = Field(..., min_length=11, max_length=20, description="手机号")


class PhoneLoginRequest(BaseModel):
    """手机验证码登录请求。"""
    phone: str = Field(..., min_length=11, max_length=20, description="手机号")
    code: str = Field(..., min_length=4, max_length=8, description="验证码")
    name: str | None = Field(None, max_length=100, description="用户名（可选）")


class WechatCallbackRequest(BaseModel):
    """微信扫码回调请求。"""
    code: str = Field(..., description="微信授权 code")
    state: str = Field("", description="state 参数（防 CSRF）")


# ── 响应 ──
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


class MembershipOut(BaseModel):
    id: str
    name: str
    rank: int
    billing_cycle: str
    processing_minutes: int
    ai_image_quota: int
    ai_video_quota: int
    storage_gb: int
    export_quota: int
    price: float

    class Config:
        from_attributes = True


class UsageOut(BaseModel):
    processing_minutes_used: int
    ai_image_used: int
    ai_video_used: int
    storage_used_mb: float
    export_used: int

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    avatar_initial: str
    notify_asset_processing: bool = True
    notify_script_generation: bool = True
    notify_marketing: bool = False
    created_at: datetime | None = None
    membership: MembershipOut | None = None
    usage: UsageOut | None = None

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """登录/注册响应：包含用户信息和 token。"""

    user: UserOut
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class SmsCodeResponse(BaseModel):
    """验证码发送响应。"""
    message: str


class WechatQrcodeResponse(BaseModel):
    """微信扫码 URL 响应。"""
    url: str
