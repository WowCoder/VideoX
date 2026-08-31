"""应用配置 — 从环境变量读取，支持 .env 文件。

所有第三方凭证均为预留项，填入 .env 后即可启用对应功能。
未配置时相关功能自动降级或返回明确提示。
"""

from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    environment: str = "development"
    # ── 数据库 ──
    database_url: str = "postgresql+asyncpg://openvma:openvma_dev@localhost:5432/openvma"
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    # 本地开发与 Docker 使用不同队列，防止遗留宿主机 Worker 截走容器任务。
    celery_task_default_queue: str = "openvma-local"

    # ── MinIO ──
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "openvma"
    minio_secret_key: str = "openvma_dev"
    minio_bucket: str = "openvma-media"
    minio_secure: bool = False
    minio_public_endpoint: str = ""
    minio_public_secure: bool = False
    max_upload_size_gb: int = 1
    minio_upload_part_size_mb: int = 16

    # ── JWT ──
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    # ── CORS ──
    cors_origins: str = "http://localhost:5273,http://localhost:3000"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"

    # ── API 防护 ──
    rate_limit_enabled: bool = False
    api_rate_limit_per_minute: int = 300
    auth_rate_limit_per_minute: int = 20
    upload_rate_limit_per_minute: int = 30

    # 只允许从已配置的供应商结果域名回收生成媒体，防止服务端请求伪造。
    ai_media_allowed_hosts: str = (
        ".aliyuncs.com,.aliyun.com,.agnes-ai.cn,.agnes-ai.space"
    )

    # ── AI Provider ──
    # 高频基础能力默认走本地模型；生成式能力默认走 DashScope。
    # Provider 必须显式选择，不做静默的本地→线上付费回退。
    ai_text_provider: str = "dashscope"
    ai_embedding_provider: str = "local"
    ai_rerank_provider: str = "local"
    ai_asr_provider: str = "local"
    ai_ocr_provider: str = "local"
    ai_vision_provider: str = "dashscope"
    ai_image_provider: str = "dashscope"
    ai_text_to_video_provider: str = "dashscope"
    ai_image_to_video_provider: str = "dashscope"
    ai_effect_video_provider: str = "dashscope"
    ai_tts_provider: str = "disabled"

    # ── 灵感岛联网发现 ──
    # 搜索结果只作为候选，后台仍会重新抓取并校验来源正文。
    web_search_provider: str = "bing-rss"
    web_search_url: str = "https://www.bing.com/search"
    web_search_timeout_seconds: float = 20.0
    web_search_results_per_query: int = 8
    inspiration_search_candidate_limit: int = 18
    inspiration_prompt_character_budget: int = 80000

    # ── 本地 AI 服务 ──
    local_ai_api_key: str = ""
    local_ai_timeout_seconds: int = 600
    local_embedding_url: str = "http://localhost:8001"
    local_rerank_url: str = "http://localhost:8002"
    local_asr_url: str = "http://localhost:8003"
    local_ocr_url: str = "http://localhost:8004"
    ai_embedding_model: str = "BAAI/bge-m3"
    ai_embedding_dimensions: int = 1024
    ai_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    ai_asr_model: str = "paraformer-zh"
    ai_ocr_model: str = "PP-OCRv4-ONNX"
    ai_match_candidate_limit: int = 20
    ai_match_result_limit: int = 5

    # ── 阿里千问 DashScope（线上生成式 AI）──
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_api_url: str = "https://dashscope.aliyuncs.com/api/v1"
    dashscope_poll_interval_seconds: float = 2.0
    dashscope_generation_timeout_seconds: int = 600
    ai_text_model: str = "qwen-plus"
    ai_vision_model: str = "qwen-vl-plus"
    ai_image_model: str = "wanx2.1-t2i-turbo"
    ai_text_to_video_model: str = "wanx2.1-t2v-turbo"
    ai_image_to_video_model: str = ""
    ai_effect_video_model: str = ""
    ai_video_resolution: str = "720P"
    ai_video_duration_seconds: int = 5
    ai_video_prompt_extend: bool = True
    ai_video_watermark: bool = False
    dashscope_embedding_model: str = "text-embedding-v3"
    dashscope_asr_model: str = "paraformer-v2"
    dashscope_ocr_model: str = "qwen-vl-ocr"

    # ── AI 配音 ──
    # 独立开关避免仅配置图像/视频后意外产生语音费用。
    ai_tts_model: str = "qwen-audio-3.0-tts-flash"
    ai_tts_voice: str = "longanfengyue"
    ai_tts_language: str = "Chinese"
    ai_tts_request_timeout_seconds: int = 120
    ai_tts_download_timeout_seconds: int = 120
    ai_tts_max_text_characters: int = 1000
    ai_tts_output_sample_rate: int = 48000
    ai_tts_output_channels: int = 2
    ai_tts_auto_time_stretch_limit: float = 1.12

    # ── Agnes AI 中国站（线上生成式 AI）──
    # 文档：https://www.agnes-ai.cn/zh-Hans/docs/overview
    agnes_api_key: str = ""
    agnes_base_url: str = "https://api.agnes-ai.cn/v1"
    agnes_poll_interval_seconds: float = 2.0
    agnes_generation_timeout_seconds: int = 600
    agnes_video_submit_interval_seconds: float = 61.0
    agnes_video_submit_max_attempts: int = 4
    agnes_video_submit_retry_seconds: float = 2.0
    agnes_text_model: str = "agnes-2.5-flash"
    agnes_vision_model: str = "agnes-2.5-flash"
    agnes_image_model: str = "agnes-image-2.1-flash"
    agnes_video_model: str = "agnes-video-2.5-flash"

    # ── 微信开放平台（扫码登录）──
    # 填入后启用：微信扫码登录/注册
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_redirect_uri: str = "http://localhost:5273/auth/wechat/callback"

    # ── 阿里云短信服务（手机验证码）──
    # 填入后启用：手机验证码登录/注册
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""
    sms_sign_name: str = "redacted"
    sms_template_code: str = "redacted"
    sms_code_ttl_seconds: int = 300
    sms_resend_interval_seconds: int = 60
    sms_hourly_limit: int = 5
    sms_daily_limit: int = 10
    sms_max_verify_attempts: int = 5

    # ── 支付宝（会员升级支付）──
    # 填入后启用：会员升级、账单、发票
    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""
    alipay_sandbox: bool = True
    alipay_notify_url: str = "http://localhost:8000/api/billing/alipay/notify"
    alipay_return_url: str = "http://localhost:5273/workspace/account"

    # ── FFmpeg 路径（可选，默认从 PATH 查找）──
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    subtitle_font_path: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def ai_media_allowed_host_list(self) -> list[str]:
        return [host.strip().lower() for host in self.ai_media_allowed_hosts.split(",") if host.strip()]

    @model_validator(mode="after")
    def validate_production_security(self):
        provider_groups = {
            "AI_TEXT_PROVIDER": (self.ai_text_provider, {"agnes", "dashscope", "disabled"}),
            "AI_EMBEDDING_PROVIDER": (self.ai_embedding_provider, {"local", "dashscope", "disabled"}),
            "AI_RERANK_PROVIDER": (self.ai_rerank_provider, {"local", "disabled"}),
            "AI_ASR_PROVIDER": (self.ai_asr_provider, {"local", "dashscope", "disabled"}),
            "AI_OCR_PROVIDER": (self.ai_ocr_provider, {"local", "dashscope", "disabled"}),
            "AI_VISION_PROVIDER": (self.ai_vision_provider, {"agnes", "dashscope", "disabled"}),
            "AI_IMAGE_PROVIDER": (self.ai_image_provider, {"agnes", "dashscope", "disabled"}),
            "AI_TEXT_TO_VIDEO_PROVIDER": (
                self.ai_text_to_video_provider,
                {"agnes", "dashscope", "disabled"},
            ),
            "AI_IMAGE_TO_VIDEO_PROVIDER": (
                self.ai_image_to_video_provider,
                {"agnes", "dashscope", "disabled"},
            ),
            "AI_EFFECT_VIDEO_PROVIDER": (
                self.ai_effect_video_provider,
                {"dashscope", "disabled"},
            ),
            "AI_TTS_PROVIDER": (self.ai_tts_provider, {"dashscope", "disabled"}),
        }
        for name, (value, allowed) in provider_groups.items():
            if value.lower() not in allowed:
                raise ValueError(f"{name} 必须是：{', '.join(sorted(allowed))}")
        if self.ai_embedding_dimensions != 1024:
            raise ValueError("当前数据库向量字段固定为 1024 维，AI_EMBEDDING_DIMENSIONS 必须为 1024")
        if self.db_pool_size < 1:
            raise ValueError("DB_POOL_SIZE 必须大于等于 1")
        if self.db_max_overflow < 0:
            raise ValueError("DB_MAX_OVERFLOW 不能小于 0")
        if self.max_upload_size_gb < 1:
            raise ValueError("MAX_UPLOAD_SIZE_GB 必须大于等于 1")
        if self.ai_match_result_limit > self.ai_match_candidate_limit:
            raise ValueError("AI_MATCH_RESULT_LIMIT 不能大于 AI_MATCH_CANDIDATE_LIMIT")
        if self.web_search_provider.lower() not in {"bing-rss", "disabled"}:
            raise ValueError("WEB_SEARCH_PROVIDER 必须是 bing-rss 或 disabled")
        if self.web_search_timeout_seconds < 5:
            raise ValueError("WEB_SEARCH_TIMEOUT_SECONDS 必须至少为 5 秒")
        if not 1 <= self.web_search_results_per_query <= 20:
            raise ValueError("WEB_SEARCH_RESULTS_PER_QUERY 必须在 1 到 20 之间")
        if not 3 <= self.inspiration_search_candidate_limit <= 50:
            raise ValueError("INSPIRATION_SEARCH_CANDIDATE_LIMIT 必须在 3 到 50 之间")
        if not 20000 <= self.inspiration_prompt_character_budget <= 200000:
            raise ValueError("INSPIRATION_PROMPT_CHARACTER_BUDGET 必须在 20000 到 200000 之间")
        if self.dashscope_poll_interval_seconds < 0.2:
            raise ValueError("DASHSCOPE_POLL_INTERVAL_SECONDS 不能小于 0.2")
        if self.dashscope_generation_timeout_seconds < 30:
            raise ValueError("DASHSCOPE_GENERATION_TIMEOUT_SECONDS 不能小于 30")
        if self.agnes_poll_interval_seconds < 0.2:
            raise ValueError("AGNES_POLL_INTERVAL_SECONDS 不能小于 0.2")
        if self.agnes_generation_timeout_seconds < 30:
            raise ValueError("AGNES_GENERATION_TIMEOUT_SECONDS 不能小于 30")
        if self.agnes_video_submit_interval_seconds < 1:
            raise ValueError("AGNES_VIDEO_SUBMIT_INTERVAL_SECONDS 不能小于 1")
        if not 1 <= self.agnes_video_submit_max_attempts <= 10:
            raise ValueError("AGNES_VIDEO_SUBMIT_MAX_ATTEMPTS 必须在 1 到 10 之间")
        if self.agnes_video_submit_retry_seconds < 0.2:
            raise ValueError("AGNES_VIDEO_SUBMIT_RETRY_SECONDS 不能小于 0.2")
        if self.ai_video_resolution not in {"720P", "1080P"}:
            raise ValueError("AI_VIDEO_RESOLUTION 必须是 720P 或 1080P")
        if not 2 <= self.ai_video_duration_seconds <= 15:
            raise ValueError("AI_VIDEO_DURATION_SECONDS 必须在 2 到 15 之间")
        if self.ai_tts_request_timeout_seconds < 30 or self.ai_tts_download_timeout_seconds < 30:
            raise ValueError("AI_TTS 请求和下载超时必须至少为 30 秒")
        if not 100 <= self.ai_tts_max_text_characters <= 5000:
            raise ValueError("AI_TTS_MAX_TEXT_CHARACTERS 必须在 100 到 5000 之间")
        if self.ai_tts_output_sample_rate not in {24000, 44100, 48000}:
            raise ValueError("AI_TTS_OUTPUT_SAMPLE_RATE 仅支持 24000、44100 或 48000")
        if self.ai_tts_output_channels not in {1, 2}:
            raise ValueError("AI_TTS_OUTPUT_CHANNELS 仅支持 1 或 2")
        if not 1.0 <= self.ai_tts_auto_time_stretch_limit <= 1.2:
            raise ValueError("AI_TTS_AUTO_TIME_STRETCH_LIMIT 必须在 1.0 到 1.2 之间")
        sms_credentials = (
            self.sms_access_key_id.strip(),
            self.sms_access_key_secret.strip(),
        )
        if any(sms_credentials) and not all(sms_credentials):
            raise ValueError("SMS_ACCESS_KEY_ID 和 SMS_ACCESS_KEY_SECRET 必须同时配置")
        if all(sms_credentials):
            if not self.sms_sign_name.strip():
                raise ValueError("启用短信服务时必须配置 SMS_SIGN_NAME")
            if not self.sms_template_code.startswith("SMS_"):
                raise ValueError("启用短信服务时 SMS_TEMPLATE_CODE 必须是 SMS_ 开头的模板编号")
        if not 60 <= self.sms_code_ttl_seconds <= 900:
            raise ValueError("SMS_CODE_TTL_SECONDS 必须在 60 到 900 之间")
        if not 30 <= self.sms_resend_interval_seconds <= 300:
            raise ValueError("SMS_RESEND_INTERVAL_SECONDS 必须在 30 到 300 之间")
        if self.sms_hourly_limit < 1:
            raise ValueError("SMS_HOURLY_LIMIT 必须大于等于 1")
        if self.sms_daily_limit < self.sms_hourly_limit:
            raise ValueError("SMS_DAILY_LIMIT 不能小于 SMS_HOURLY_LIMIT")
        if not 1 <= self.sms_max_verify_attempts <= 10:
            raise ValueError("SMS_MAX_VERIFY_ATTEMPTS 必须在 1 到 10 之间")

        if self.environment.lower() != "production":
            return self
        if self.jwt_secret == "dev-secret-change-in-production" or len(self.jwt_secret) < 32:
            raise ValueError("生产环境必须配置至少 32 位的 JWT_SECRET")
        if not self.cors_origin_list or any(
            origin == "*" or not origin.startswith("https://") for origin in self.cors_origin_list
        ):
            raise ValueError("生产环境 CORS_ORIGINS 必须是明确的 HTTPS 来源，不能使用通配符")
        if not self.trusted_host_list or "*" in self.trusted_host_list:
            raise ValueError("生产环境必须配置明确的 TRUSTED_HOSTS")
        if not self.rate_limit_enabled:
            raise ValueError("生产环境必须启用 RATE_LIMIT_ENABLED")
        if not self.minio_public_endpoint:
            raise ValueError("生产环境必须配置 MINIO_PUBLIC_ENDPOINT")
        if not self.minio_public_secure:
            raise ValueError("生产环境 MINIO_PUBLIC_SECURE 必须为 true")
        uses_local_ai = any(
            provider.lower() == "local"
            for provider in (
                self.ai_embedding_provider,
                self.ai_rerank_provider,
                self.ai_asr_provider,
                self.ai_ocr_provider,
            )
        )
        if uses_local_ai and len(self.local_ai_api_key) < 24:
            raise ValueError("生产环境启用本地 AI 时必须配置至少 24 位的 LOCAL_AI_API_KEY")
        return self

    @property
    def has_dashscope(self) -> bool:
        return bool(self.dashscope_api_key)

    @property
    def has_agnes(self) -> bool:
        return bool(self.agnes_api_key)

    def _provider_available(self, provider: str) -> bool:
        if provider.lower() == "dashscope":
            return self.has_dashscope
        if provider.lower() == "agnes":
            return self.has_agnes
        return False

    @property
    def has_text_generation(self) -> bool:
        return self._provider_available(self.ai_text_provider) and bool(self.active_text_model)

    @property
    def has_embedding(self) -> bool:
        if self.ai_embedding_provider.lower() == "local":
            return bool(self.local_embedding_url)
        if self.ai_embedding_provider.lower() == "dashscope":
            return self.has_dashscope
        return False

    @property
    def has_rerank(self) -> bool:
        return self.ai_rerank_provider.lower() == "local" and bool(self.local_rerank_url)

    @property
    def has_asr(self) -> bool:
        if self.ai_asr_provider.lower() == "local":
            return bool(self.local_asr_url)
        if self.ai_asr_provider.lower() == "dashscope":
            return self.has_dashscope
        return False

    @property
    def has_ocr(self) -> bool:
        if self.ai_ocr_provider.lower() == "local":
            return bool(self.local_ocr_url)
        if self.ai_ocr_provider.lower() == "dashscope":
            return self.has_dashscope
        return False

    @property
    def has_vision(self) -> bool:
        return self._provider_available(self.ai_vision_provider) and bool(self.active_vision_model)

    @property
    def has_image_generation(self) -> bool:
        return self._provider_available(self.ai_image_provider) and bool(self.active_image_model)

    @property
    def has_text_to_video(self) -> bool:
        return (
            self._provider_available(self.ai_text_to_video_provider)
            and bool(self.active_text_to_video_model)
        )

    @property
    def has_image_to_video(self) -> bool:
        return (
            self._provider_available(self.ai_image_to_video_provider)
            and bool(self.active_image_to_video_model)
        )

    @property
    def has_effect_video(self) -> bool:
        return (
            self.ai_effect_video_provider.lower() == "dashscope"
            and self.has_dashscope
            and bool(self.ai_effect_video_model)
        )

    @property
    def has_tts(self) -> bool:
        return (
            self.ai_tts_provider.lower() == "dashscope"
            and self.has_dashscope
            and bool(self.ai_tts_model and self.ai_tts_voice)
        )

    @property
    def active_embedding_model(self) -> str:
        if self.ai_embedding_provider.lower() == "dashscope":
            return self.dashscope_embedding_model
        return self.ai_embedding_model

    @property
    def active_text_model(self) -> str:
        return (
            self.agnes_text_model
            if self.ai_text_provider.lower() == "agnes"
            else self.ai_text_model
        )

    @property
    def active_vision_model(self) -> str:
        return (
            self.agnes_vision_model
            if self.ai_vision_provider.lower() == "agnes"
            else self.ai_vision_model
        )

    @property
    def active_image_model(self) -> str:
        return (
            self.agnes_image_model
            if self.ai_image_provider.lower() == "agnes"
            else self.ai_image_model
        )

    @property
    def active_text_to_video_model(self) -> str:
        return (
            self.agnes_video_model
            if self.ai_text_to_video_provider.lower() == "agnes"
            else self.ai_text_to_video_model
        )

    @property
    def active_image_to_video_model(self) -> str:
        return (
            self.agnes_video_model
            if self.ai_image_to_video_provider.lower() == "agnes"
            else self.ai_image_to_video_model
        )

    @property
    def has_wechat(self) -> bool:
        return bool(self.wechat_app_id and self.wechat_app_secret)

    @property
    def has_sms(self) -> bool:
        return all(
            value.strip()
            for value in (
                self.sms_access_key_id,
                self.sms_access_key_secret,
                self.sms_sign_name,
                self.sms_template_code,
            )
        )

    @property
    def has_alipay(self) -> bool:
        return bool(self.alipay_app_id and self.alipay_private_key)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 同一个生产 env 文件也供 Compose、PostgreSQL、Redis 和 Nginx 使用。
        # 应用只读取自己声明的配置项，第三方服务变量由对应容器消费。
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
