# 配置说明

[返回 README](../README.md) · [快速开始](getting-started.md) · [配置源码](../backend/app/config.py)

## 环境文件与代理

本地从根目录 [`.env.example`](../.env.example) 复制 `.env`。示例关闭所有 AI Provider，适合先验证人工媒体链路。Settings 读取仓库根 `.env`，进程环境变量优先；配置在进程内缓存，修改后重启宿主机 API/Worker/Beat。

Compose 从根 `.env` 做变量替换，并为各服务设置内部数据库、Redis、MinIO 和本地 AI 地址。容器环境变化须用 `docker compose up -d` 重新创建服务。不要把生产 `.env.production` 复制为开发配置。

前端 Vite 使用 **服务端变量** `API_PROXY_TARGET`，宿主机默认 `http://localhost:8000`，Compose 前端设置 `http://backend:8000`。它不带 `VITE_` 前缀，不注入浏览器 JavaScript；浏览器通过同源 `/api` 和 WebSocket 访问后端。见 [Vite 配置](../frontend/vite.config.ts)。

Pages 只需要可选 `PAGES_BASE_PATH`（默认 `/VideoX/`），不使用应用凭证。所有 API Key、JWT、数据库和管理员密钥留在服务端。

## Provider 支持矩阵

| 配置项 | 支持值 |
| --- | --- |
| `AI_EMBEDDING_PROVIDER` | `local` / `dashscope` / `disabled` |
| `AI_RERANK_PROVIDER` | `local` / `disabled` |
| `AI_ASR_PROVIDER`、`AI_OCR_PROVIDER` | `local` / `dashscope` / `disabled` |
| `AI_TEXT_PROVIDER`、`AI_VISION_PROVIDER`、`AI_IMAGE_PROVIDER` | `agnes` / `dashscope` / `disabled` |
| `AI_TEXT_TO_VIDEO_PROVIDER`、`AI_IMAGE_TO_VIDEO_PROVIDER` | `agnes` / `dashscope` / `disabled` |
| `AI_EFFECT_VIDEO_PROVIDER` | `dashscope` / `disabled` |
| `AI_TTS_PROVIDER` | `dashscope` / `disabled` |
| `WEB_SEARCH_PROVIDER` | `bing-rss` / `disabled` |

Settings 验证支持值。`.env.example` 是安全启动基线；代码类和 Compose 的回退默认值不应当作为关闭 AI 的替代品。删除示例中 Provider 行之前先检查默认行为。

本地四项服务地址分别是 `LOCAL_EMBEDDING_URL`、`LOCAL_RERANK_URL`、`LOCAL_ASR_URL`、`LOCAL_OCR_URL`；宿主机对应 8001–8004，Compose 覆盖为服务名。`LOCAL_AI_API_KEY` 必须在客户端和服务端一致，生产启用本地能力时至少 24 位。模型设备使用 `LOCAL_AI_DEVICE`，下载来源使用 `LOCAL_MODEL_SOURCE`。

Embedding 字段固定 1024 维，`AI_EMBEDDING_DIMENSIONS` 不能任意更改。切换 BGE-M3 与 DashScope 模型后须重建向量，不得混用相同维度的不同模型空间。

## 云端能力：显式启用

下面仅启用文本，其他能力保持 `disabled`：

```dotenv
AI_TEXT_PROVIDER=dashscope
DASHSCOPE_API_KEY=your-own-service-key
AI_TEXT_MODEL=qwen-plus
```

使用 Agnes 文本时替换为：

```dotenv
AI_TEXT_PROVIDER=agnes
AGNES_API_KEY=your-own-service-key
AGNES_TEXT_MODEL=your-enabled-model
```

DashScope 文本/视觉/图片/视频分别配置 `AI_TEXT_MODEL`、`AI_VISION_MODEL`、`AI_IMAGE_MODEL`、`AI_TEXT_TO_VIDEO_MODEL`、`AI_IMAGE_TO_VIDEO_MODEL`；草图动效使用 `AI_EFFECT_VIDEO_MODEL`。Agnes 对应 `AGNES_TEXT_MODEL`、`AGNES_VISION_MODEL`、`AGNES_IMAGE_MODEL`、`AGNES_VIDEO_MODEL`。模型名必须与部署者已开通的服务匹配，示例不是可用性或费用承诺。

`DASHSCOPE_BASE_URL` 与 `DASHSCOPE_API_URL` 分别用于兼容文本接口和原生媒体接口；Agnes 使用 `AGNES_BASE_URL`。Provider 决定协议适配，不能只把 URL 换成另一个任意服务就认为兼容。

`AI_MEDIA_ALLOWED_HOSTS` 限制生成结果回收地址。确需扩展时仅添加已确认的供应商域名，不使用通配全部主机。视频参数包括 `AI_VIDEO_RESOLUTION`、`AI_VIDEO_DURATION_SECONDS`、`AI_VIDEO_PROMPT_EXTEND` 和 `AI_VIDEO_WATERMARK`，实际能力由 Provider/模型约束。

配音单独配置：

```dotenv
AI_TTS_PROVIDER=dashscope
AI_TTS_MODEL=your-enabled-tts-model
AI_TTS_VOICE=your-supported-voice
AI_TTS_LANGUAGE=Chinese
```

TTS 使用 `DASHSCOPE_API_KEY`，并有请求/下载超时、文本分段与时长适配设置。配置凭证不会自动启用已关闭的能力；操作失败不会静默回退到另一个付费 Provider。

## 搜索与灵感监测

`WEB_SEARCH_URL`、`WEB_SEARCH_TIMEOUT_SECONDS`、`WEB_SEARCH_RESULTS_PER_QUERY` 控制搜索请求；`INSPIRATION_SEARCH_CANDIDATE_LIMIT` 与 `INSPIRATION_PROMPT_CHARACTER_BUDGET` 控制候选与模型上下文预算。用户指定来源策略由灵感任务配置保存。

搜索和抓取需要网络访问。选题生成需要显式启用文本模型；链接监测即使没有有效变化也会保存实际来源状态。首次基线不产生变化总结，详见 [架构](architecture.md)。

## 任务队列与并发

`CELERY_TASK_DEFAULT_QUEUE` 既是默认队列，也是未显式设置其他队列时的基名：

```text
<base>
<base>.control
<base>.short-ai
<base>.video
<base>.media
<base>.export
```

可用 `CELERY_CONTROL_QUEUE`、`CELERY_SHORT_AI_QUEUE`、`CELERY_VIDEO_QUEUE`、`CELERY_MEDIA_QUEUE`、`CELERY_EXPORT_QUEUE` 单独覆盖。宿主机基名默认 `openvma-local`，开发 Compose 为 `openvma-docker`；不要让不同代码版本 Worker 争抢同一队列。

`VIDEO_QUEUE_MAX_PER_USER/PROJECT/GLOBAL` 是排队容量；`VIDEO_INFLIGHT_MAX_PER_USER/PROJECT/GLOBAL` 是供应商在途并发，不等于 Celery Worker 并发。`VIDEO_BATCH_MAX_SHOTS` 限制单批次规模，`VIDEO_DISPATCH_INTERVAL_SECONDS`、`VIDEO_POLL_INTERVAL_SECONDS`、`VIDEO_PROVIDER_TIMEOUT_SECONDS` 控制调度、查询和等待上限。

`JOB_QUEUE_WARNING_SECONDS`、`JOB_QUEUE_MAX_AGE_SECONDS`、`JOB_HEARTBEAT_TIMEOUT_SECONDS` 控制任务滞留与恢复判定。降低阈值前评估真实媒体耗时。Agnes 还有独立提交间隔、重试次数和退避配置。

## 存储与身份

- `DATABASE_URL`：异步 PostgreSQL URL；`REDIS_URL`：消息与状态连接。
- `MINIO_ENDPOINT`：服务端访问地址；`MINIO_PUBLIC_ENDPOINT`：浏览器可达媒体地址；协议使用对应 secure 选项。
- `MAX_UPLOAD_SIZE_GB`：上传上限；默认 1 GiB，代理层也需匹配。
- `JWT_SECRET`：普通账号鉴权；管理员使用独立 `ADMIN_JWT_SECRET` 与 `ADMIN_MFA_ENCRYPTION_KEY`。
- `CORS_ORIGINS`、`TRUSTED_HOSTS`：部署入口；生产开启 `RATE_LIMIT_ENABLED`。
- `SMS_ACCESS_KEY_ID/SECRET`、`SMS_SIGN_NAME`、`SMS_TEMPLATE_CODE`：部署者自己的阿里云短信身份和模板，参数需包含 `${code}`；不随仓库提供实际运营身份。
- `WECHAT_APP_ID/SECRET` 与 `WECHAT_REDIRECT_URI`：部署者自己的微信开放平台配置。
- `ALIPAY_*`：支付账号、签名材料和回调；默认沙箱不能代替正式商户接入。

## 生产配置

以 [`.env.production.example`](../.env.production.example) 为起点，按照 [生产手册](../deploy/README.md) 替换域名、数据库/Redis/MinIO 凭证、用户与管理密钥。管理员与媒体域名示例为 `admin.example.com`、`media.example.com`，均需部署者自己的 DNS 和证书。

生产验证保持严格，不复用开发默认密钥。修改 Provider 或凭证后，通过不可变镜像发布流程更新 API/Worker；发布前先验证配置，避免输出包含密钥的完整 Compose 配置到公共日志。
