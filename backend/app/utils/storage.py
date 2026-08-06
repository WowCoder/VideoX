"""MinIO 对象存储工具。"""

from minio import Minio
from minio.error import S3Error
from io import BytesIO
from datetime import datetime, timezone
from typing import BinaryIO, Optional

from app.config import get_settings

settings = get_settings()

_client: Optional[Minio] = None
_public_client: Optional[Minio] = None


def get_minio_client() -> Minio:
    """获取 MinIO 客户端（单例）。"""
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        # 确保 bucket 存在
        if not _client.bucket_exists(settings.minio_bucket):
            _client.make_bucket(settings.minio_bucket)
    return _client


def get_public_minio_client() -> Minio:
    """仅用于生成浏览器可访问的签名 URL，不执行 bucket 管理。"""
    global _public_client
    if _public_client is None:
        _public_client = Minio(
            settings.minio_public_endpoint or settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_public_secure if settings.minio_public_endpoint else settings.minio_secure,
            # 公开地址可能只对浏览器可达，显式指定 MinIO 默认区域，避免 SDK
            # 为生成签名 URL 先从该公开地址请求 bucket location。
            region="us-east-1",
        )
    return _public_client


def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传文件到 MinIO，返回对象 key。"""
    client = get_minio_client()
    client.put_object(
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def upload_stream(
    object_name: str,
    stream: BinaryIO,
    length: int,
    content_type: str = "application/octet-stream",
) -> str:
    """将文件流分片上传到 MinIO，不在应用内存中构造完整文件副本。"""
    client = get_minio_client()
    client.put_object(
        settings.minio_bucket,
        object_name,
        stream,
        length=length,
        part_size=max(5, settings.minio_upload_part_size_mb) * 1024 * 1024,
        content_type=content_type,
    )
    return object_name


def get_file_url(object_name: str, expires_hours: int = 24) -> str:
    """获取文件的预签名 URL。"""
    client = get_public_minio_client()
    from datetime import timedelta
    return client.presigned_get_object(
        settings.minio_bucket,
        object_name,
        expires=timedelta(hours=expires_hours),
    )


def download_file(object_name: str, local_path: str) -> str:
    """将 MinIO 对象下载到指定本地路径。"""
    client = get_minio_client()
    client.fget_object(settings.minio_bucket, object_name, local_path)
    return local_path


def delete_file(object_name: str) -> bool:
    """删除文件。"""
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, object_name)
        return True
    except S3Error:
        return False
