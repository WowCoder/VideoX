"""独立管理员 JWT、可撤销刷新令牌、MFA 加密和 TOTP。"""

import base64
import hashlib
import hmac
import io
import secrets
import struct
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import jwt

from app.config import get_settings


ADMIN_AUDIENCE = "videox-admin"
ADMIN_ACCESS_TYPE = "admin_access"
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def as_utc(value: datetime) -> datetime:
    """Normalize database datetimes for PostgreSQL and lightweight test doubles."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _settings():
    return get_settings()


def _admin_jwt_secret() -> str:
    settings = _settings()
    return settings.admin_jwt_secret or settings.jwt_secret


def _mfa_key_material() -> bytes:
    settings = _settings()
    raw = settings.admin_mfa_encryption_key or f"development:{settings.jwt_secret}"
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())


def encrypt_mfa_secret(secret: str) -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("cryptography 未安装，无法安全保存管理员 MFA 密钥") from exc
    return Fernet(_mfa_key_material()).encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_mfa_secret(encrypted: str) -> str:
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("cryptography 未安装，无法验证管理员 MFA") from exc
    try:
        return Fernet(_mfa_key_material()).decrypt(encrypted.encode("ascii")).decode("ascii")
    except InvalidToken as exc:
        raise RuntimeError("管理员 MFA 密钥无法解密，请检查 ADMIN_MFA_ENCRYPTION_KEY") from exc


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_totp_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def totp_code(secret: str, *, at_time: int | None = None) -> str:
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // TOTP_PERIOD_SECONDS
    digest = hmac.new(
        _decode_totp_secret(secret),
        struct.pack(">Q", counter),
        hashlib.sha1,
    ).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp(secret: str, code: str, *, at_time: int | None = None, window: int = 1) -> bool:
    normalized = "".join(character for character in code if character.isdigit())
    if len(normalized) != TOTP_DIGITS:
        return False
    timestamp = int(time.time() if at_time is None else at_time)
    return any(
        hmac.compare_digest(
            totp_code(secret, at_time=timestamp + offset * TOTP_PERIOD_SECONDS),
            normalized,
        )
        for offset in range(-window, window + 1)
    )


def totp_provisioning_uri(secret: str, email: str, issuer: str = "VideoX Admin") -> str:
    label = quote(f"{issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={quote(secret)}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )


def _totp_qr(uri: str):
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("qrcode 未安装，无法显示管理员 MFA 二维码") from exc

    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    return qr


def print_totp_qr(uri: str, *, out=None) -> None:
    """Print an offline QR code, forcing stable black/white colors on a TTY."""
    output = out or sys.stdout
    _totp_qr(uri).print_ascii(
        out=output,
        tty=bool(getattr(output, "isatty", lambda: False)()),
        invert=False,
    )


def totp_qr_ascii(uri: str) -> str:
    """Return a plain-text QR code for tests and non-interactive fallbacks."""
    output = io.StringIO()
    print_totp_qr(uri, out=output)
    return output.getvalue()


def create_admin_access_token(admin_id: str, session_id: str, token_version: int) -> str:
    settings = _settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "sid": session_id,
        "ver": token_version,
        "type": ADMIN_ACCESS_TYPE,
        "aud": ADMIN_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.admin_access_expire_minutes),
    }
    return jwt.encode(payload, _admin_jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_admin_access_token(token: str) -> dict | None:
    settings = _settings()
    try:
        payload = jwt.decode(
            token,
            _admin_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            audience=ADMIN_AUDIENCE,
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != ADMIN_ACCESS_TYPE:
        return None
    return payload


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=_settings().admin_session_expire_days)
