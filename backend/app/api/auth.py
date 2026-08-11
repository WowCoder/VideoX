"""鉴权路由：注册/登录/刷新 token/手机验证码/微信扫码。"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User, Membership, Usage
from app.schemas.auth import (
    RegisterRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserOut, AuthResponse,
    MembershipOut, UsageOut, SubscriptionOut,
    UserSettingsUpdate,
    PhoneCodeRequest, PhoneLoginRequest, WechatCallbackRequest,
    SmsCodeResponse, WechatQrcodeResponse,
)
from app.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from app.dependencies import get_current_user
from app.services.sms_provider import send_code, verify_code
from app.services.wechat_provider import (
    get_qrcode_url, exchange_code_for_token, get_user_info,
)
from app.services.subscriptions import reconcile_user_subscription

router = APIRouter()
logger = logging.getLogger(__name__)


async def _ensure_default_membership(db: AsyncSession):
    """确保默认 Free 会员方案存在。"""
    result = await db.execute(select(Membership).where(Membership.id == "membership-free"))
    if not result.scalar_one_or_none():
        free = Membership(
            id="membership-free",
            name="Free",
            rank=0,
            billing_cycle="monthly",
            processing_minutes=60,
            ai_image_quota=10,
            ai_video_quota=5,
            storage_gb=5,
            export_quota=10,
            price=0.0,
        )
        db.add(free)


async def _serialize_user(user: User) -> UserOut:
    """序列化用户（带 membership 和 usage）。"""
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_initial=user.avatar_initial,
        notify_asset_processing=user.notify_asset_processing,
        notify_script_generation=user.notify_script_generation,
        notify_marketing=user.notify_marketing,
        created_at=user.created_at,
        membership=MembershipOut.model_validate(user.membership) if user.membership else None,
        usage=UsageOut.model_validate(user.usage) if user.usage else None,
        subscription=(
            SubscriptionOut.model_validate(user.subscription) if user.subscription else None
        ),
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册。"""
    await _ensure_default_membership(db)
    normalized_email = str(req.email).strip().lower()

    # 检查邮箱是否已注册
    existing = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 创建用户
    user = User(
        email=normalized_email,
        name=req.name,
        password_hash=hash_password(req.password),
        avatar_initial=req.name[0].upper() if req.name else "U",
        membership_id="membership-free",
    )
    db.add(user)
    await db.flush()

    # 创建用量记录
    usage = Usage(user_id=user.id)
    db.add(usage)
    await db.flush()

    # 加载关联
    result = await db.execute(
        select(User)
        .where(User.id == user.id)
        .options(
            selectinload(User.membership),
            selectinload(User.usage),
            selectinload(User.subscription),
        )
    )
    user = result.scalar_one()
    await reconcile_user_subscription(db, user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return AuthResponse(
        user=await _serialize_user(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录。"""
    result = await db.execute(
        select(User)
        .where(func.lower(User.email) == str(req.email).strip().lower())
        .options(
            selectinload(User.membership),
            selectinload(User.usage),
            selectinload(User.subscription),
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    await reconcile_user_subscription(db, user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return AuthResponse(
        user=await _serialize_user(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest):
    """刷新 access token。"""
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="无效的 refresh token")

    user_id = payload.get("sub")
    access_token = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=1800,
    )


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    req: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户资料和通知偏好。"""
    normalized_email = str(req.email).strip().lower()
    email_owner = await db.execute(
        select(User).where(func.lower(User.email) == normalized_email, User.id != user.id)
    )
    if email_owner.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该邮箱已被其他账户使用")

    user.name = req.name.strip()
    user.email = normalized_email
    user.avatar_initial = user.name[0].upper()
    user.notify_asset_processing = req.notify_asset_processing
    user.notify_script_generation = req.notify_script_generation
    user.notify_marketing = req.notify_marketing
    await db.flush()
    return await _serialize_user(user)


# ── 手机验证码登录 ──

async def _find_or_create_user_by_email(
    db: AsyncSession,
    email: str,
    name: str,
) -> User:
    """通过 email 查找或创建用户（用于手机/微信登录）。

    由于 User 模型没有 phone / openid 字段，使用构造的 email 作为唯一标识：
    - 手机登录：phone@openvma.cn
    - 微信登录：wx_{openid}@openvma.cn

    无密码登录的用户 password_hash 设置为随机值（无法通过密码登录）。
    """
    result = await db.execute(
        select(User)
        .where(User.email == email)
        .options(
            selectinload(User.membership),
            selectinload(User.usage),
            selectinload(User.subscription),
        )
    )
    user = result.scalar_one_or_none()

    if user:
        await reconcile_user_subscription(db, user)
        return user

    # 创建新用户
    await _ensure_default_membership(db)
    user = User(
        email=email,
        name=name,
        password_hash=hash_password(str(uuid.uuid4())),
        avatar_initial=name[0].upper() if name else "U",
        membership_id="membership-free",
    )
    db.add(user)
    await db.flush()

    # 创建用量记录
    usage = Usage(user_id=user.id)
    db.add(usage)
    await db.flush()

    # 重新加载关联
    result = await db.execute(
        select(User)
        .where(User.id == user.id)
        .options(
            selectinload(User.membership),
            selectinload(User.usage),
            selectinload(User.subscription),
        )
    )
    user = result.scalar_one()
    await reconcile_user_subscription(db, user)
    return user


async def _issue_tokens(user: User) -> AuthResponse:
    """为用户签发 access_token / refresh_token 并返回 AuthResponse。"""
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return AuthResponse(
        user=await _serialize_user(user),
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/send-code", response_model=SmsCodeResponse)
async def send_sms_code(req: PhoneCodeRequest):
    """发送手机验证码。

    调用 sms_provider.send_code 发送真实验证码。
    未配置短信凭证时返回 503。
    """
    from app.config import get_settings
    if not get_settings().has_sms:
        raise HTTPException(status_code=503, detail="短信服务未配置，请使用邮箱登录")
    success = await send_code(req.phone)
    if not success:
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")
    return SmsCodeResponse(message="验证码已发送")


@router.post("/login-phone", response_model=AuthResponse)
async def login_with_phone(
    req: PhoneLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """手机验证码登录。

    验证码通过后，查找或创建用户（email = phone@openvma.cn）。
    """
    # 验证验证码
    if not await verify_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")

    # 查找或创建用户
    email = f"{req.phone}@openvma.cn"
    name = req.name or f"用户{req.phone[-4:]}"
    user = await _find_or_create_user_by_email(db, email, name)

    return await _issue_tokens(user)


# ── 微信扫码登录 ──

@router.get("/wechat/qrcode", response_model=WechatQrcodeResponse)
async def get_wechat_qrcode(state: str = ""):
    """获取微信扫码登录 URL。

    前端拿到 URL 后跳转或嵌入二维码。
    未配置微信凭证时返回 503。
    """
    try:
        url = get_qrcode_url(state)
        return WechatQrcodeResponse(url=url)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/wechat/callback", response_model=AuthResponse)
async def wechat_callback(
    req: WechatCallbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """微信扫码回调。

    用 code 换 access_token，获取用户信息，查找或创建用户。
    未配置微信凭证时返回 503。
    """
    try:
        token_data = await exchange_code_for_token(req.code)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("微信换取 token 失败：%s", e)
        raise HTTPException(status_code=400, detail=f"微信授权失败：{str(e)}")

    openid = token_data.get("openid", "")
    access_token = token_data.get("access_token", "")
    if not openid or not access_token:
        err = token_data.get("errmsg", "未知错误")
        raise HTTPException(status_code=400, detail=f"微信授权失败：{err}")

    # 获取用户信息
    try:
        wx_user = await get_user_info(access_token, openid)
    except Exception as e:
        logger.error("获取微信用户信息失败：%s", e)
        raise HTTPException(status_code=400, detail=f"获取微信用户信息失败：{str(e)}")

    nickname = wx_user.get("nickname", "微信用户")

    # 查找或创建用户（用 openid 构造 email 作为唯一标识）
    email = f"wx_{openid}@openvma.cn"
    user = await _find_or_create_user_by_email(db, email, nickname)

    return await _issue_tokens(user)
