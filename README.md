# OpenVMA

OpenVMA 是一个面向 Desktop Web 的智能视频素材管理、脚本创作、真实素材匹配、时间线剪辑与成片导出系统。本仓库包含可运行的 React 前端、FastAPI 后端、Celery 异步任务、PostgreSQL/pgvector、Redis、MinIO、FFmpeg 媒体处理，以及“本地基础 AI + 线上生成式 AI”的混合模型架构。

## 核心原则

- 项目、素材、片段、脚本、分镜、任务、时间线、订单、用量、协作者和发票申请均来自真实后端与数据库。
- 无数据展示真实空状态，请求失败展示真实错误和重试入口。
- 不使用业务 Mock、固定示例数据、固定验证码、模拟进度、定时假完成或假成功提示。
- FFmpeg、AI 和第三方任务只有在真实完成后才能写入 `SUCCEEDED`，配额也只在首次真实成功后扣减。
- 本地 AI 失败不会静默回退到线上付费调用；是否使用 DashScope 必须通过 Provider 显式配置。
- 不同 Embedding 模型的向量空间不得混用，即使输出维度相同。

## 当前能力

| 模块 | 实现状态 | 数据/执行来源 |
| --- | --- | --- |
| 登录、用户资料、通知偏好 | 已实现 | PostgreSQL、JWT |
| 项目与团队协作 | 已实现 | owner/editor/viewer 真实权限与邀请 Token |
| 视频与音频上传校验 | 已实现 | 流式 MinIO 上传、Magic Bytes、FFprobe；支持常见视频及 MP3/WAV/M4A/AAC/FLAC/OGG |
| 视频素材处理 | 已实现 | FFmpeg、真实 ASR/OCR、镜头切分、缩略图、Clip 入库 |
| 音频素材处理 | 已实现 | FFprobe 元数据、AAC/M4A 标准化试听文件、独立音频素材库 |
| 语义索引与镜头匹配 | 已实现 | BGE-M3/text-embedding-v3、pgvector、可选 BGE Reranker |
| 脚本与分镜 | 已实现 | PostgreSQL；AI 脚本需真实文本模型 |
| AI 初剪 | 已实现真实素材匹配与时间线装配 | Embedding、pgvector、后端确定性代码 |
| 缺失镜头生成 | 分镜级生图/图生视频任务已实现 | 需要真实 DashScope 模型与凭证；初剪不会假装自动生成 |
| 时间线编辑 | 已实现 | 真实版本号、冲突控制、视频/音频移动、裁剪、分割、转场、音量、静音、降噪、淡入淡出 |
| 视频导出 | 已实现 | FFmpeg Filter Graph，多轨音频混音，MP4/MOV/ProRes |
| 任务中心 | 已实现 | Celery、Redis、暂停/继续、取消、恢复、Watchdog |
| 通知中心与全局搜索 | 已实现 | PostgreSQL、精准跳转 |
| 支付和发票 | 部分实现 | 订单/申请真实；支付宝和正式税务服务需外部凭证 |

### Desktop 当前交互约定

- 素材库采用主从两栏：左侧素材列表可连续切换视频或音频，右侧常驻详情展示真实媒体；视频展示标签、完整对白、OCR 和 Clip 级人物/物品/场景信息，音频展示试听与编码、采样率、声道、码率。
- 素材搜索会返回真实命中字段与命中摘要，搜索范围包括名称、标签、对白、OCR 和 Clip 语义文本，不为缺失字段生成展示内容。
- 脚本搜索覆盖标题、摘要、台词、画面意图和分镜描述；脚本正文中的台词、画面意图与分镜描述均可编辑并持久化。
- 素材匹配以 `Shot` 为最小单位。每个分镜独立生成查询、召回和写入候选，异步 Job 的真实进度会回流页面，完成后自动刷新候选。
- “AI 完善所选”会明确提示它将执行一次线上文本模型调用；不会在普通保存、素材匹配或页面刷新时隐式调用付费模型。
- “创建初剪项目”会创建独立项目和内部任务快照。快照通过 `is_snapshot` 标识并从脚本中心隐藏，原脚本不会被覆盖。

## 技术架构

```text
React + TypeScript + Vite + History API Router
          │
          ▼
FastAPI ───────── PostgreSQL + pgvector
  │                     │
  ├──────── Redis ──────┤
  │          │          │
  │          ▼          │
  │      Celery Worker  │
  │          │          │
  │          ├── FFmpeg / FFprobe
  │          ├── MinIO
  │          ├── Local Embedding / Reranker / ASR / OCR
  │          └── DashScope 文本 / 生图 / 视频生成
  │
  └── WebSocket 任务状态推送
```

## AI 模型方案

### 本地核心模型服务

| 服务 | 默认模型/运行时 | 端口 | 用途 |
| --- | --- | ---: | --- |
| Embedding | `BAAI/bge-m3` | 8001 | 素材和脚本查询的 1024 维向量 |
| Reranker | `BAAI/bge-reranker-v2-m3` | 8002 | 对 pgvector 召回候选进行二次排序 |
| ASR | FunASR Paraformer + VAD + 标点 | 8003 | 视频语音转写 |
| OCR | PP-OCR ONNX / RapidOCR | 8004 | 视频抽帧文字识别；兼容 Apple Silicon |

镜头切分、音频提取、转码和导出由 FFmpeg 完成，不需要 AI 模型。

### 线上生成式模型

| 能力 | 默认/配置项 | 说明 |
| --- | --- | --- |
| AI 脚本 | `AI_TEXT_MODEL=qwen-plus` | 结构化脚本生成 |
| AI 生图 | `AI_IMAGE_MODEL=wanx2.1-t2i-turbo` | 分镜关键帧生成，模型名需以账号实际可用为准 |
| 文生视频 | `AI_TEXT_TO_VIDEO_MODEL` | 必须独立配置并执行真实冒烟测试 |
| 图生视频 | `AI_IMAGE_TO_VIDEO_MODEL=wan2.7-i2v-2026-04-25` | 关键帧作为 `first_frame`，使用万相 2.7 原生 `media` 协议 |
| AI 草图视频 | `AI_EFFECT_VIDEO_MODEL=wan2.7-i2v-2026-04-25` | Canvas 草图作为首帧，动效描述作为 Prompt；与普通图生视频保持独立能力入口 |

一个 `DASHSCOPE_API_KEY` 可以认证多个已开通模型，但模型权限、地域、并发、限流和费用分别计算。

## 目录结构

```text
OpenVMA/
├── backend/                 FastAPI、Celery、Alembic、业务模型与测试
│   ├── app/
│   ├── alembic/
│   ├── scripts/
│   └── tests/
├── frontend/                Desktop React 前端
├── local-ai/
│   ├── embedding/           BGE-M3 服务
│   ├── reranker/            BGE Reranker 服务
│   ├── asr/                 FunASR 服务
│   └── ocr/                 PP-OCR ONNX 服务
├── docker-compose.yml
├── compose.prod.yml          生产 Compose（雷池后的内部网关）
├── deploy/                   发布、备份、回滚与雷池配置手册
├── Makefile                 常用开发、检查和维护命令
└── .env.example
```

Desktop 路由由 `frontend/src/router.tsx` 和 `frontend/src/routes/index.tsx`
提供路径参数、鉴权守卫、查询参数、懒加载与浏览器前进后退支持，不依赖第三方路由运行时。
Backend、Celery Worker 与 Celery Beat 的 Docker 进程默认使用非 root 的 `openvma` 用户运行。

## 环境要求

基础服务：

- Docker Desktop / Docker Engine + Compose
- Node.js 20 或更高版本
- Python 3.11/3.12（非 Docker 开发）
- FFmpeg、FFprobe（非 Docker Worker）

本地 AI：

- CPU 可以运行全部基础模型，但首次模型下载和长视频处理需要时间。
- NVIDIA GPU 可通过相应运行时加速，具体显存取决于模型、批量和输入长度。
- Apple Silicon 默认使用 CPU；OCR 使用 PP-OCR ONNX，避免依赖缺少 Linux ARM Wheel 的 PaddlePaddle。
- 模型权重会持久化到 Docker Volume，不会每次启动重新下载。

## 快速启动

> 根目录的 `docker-compose.yml` 面向本地开发和测试：包含源码挂载、Vite 开发服务器、Uvicorn reload、固定开发凭证及本机端口映射，不应直接作为公网生产部署模板。

生产部署请使用 `compose.prod.yml`，并从 `deploy/README.md` 开始；首次上线后的日常发布与回滚参见 `deploy/release.md`。推荐公网入口为雷池 SafeLine，仓库内 Nginx 只作为受保护的内部上游。

运营后台使用同一前端依赖树中的独立 Vite 构建，开发入口为 `npm run dev:admin`，生产入口为独立 `admin-gateway` 和 `ADMIN_DOMAIN`。用户网关明确隐藏 `/api/admin/*` 与 `/admin.html`，后台网关只代理 `/api/admin/*`。管理员账号通过 `backend/scripts/manage_admin.py` 单独维护，并强制使用 TOTP MFA。

### 1. 创建环境配置

```bash
cp .env.example .env
```

开发环境可以暂时不填第三方凭证。本地 AI 建议设置一个随机 Token：

```env
LOCAL_AI_API_KEY=请替换为至少24位随机字符串
```

生产环境启用本地 AI 时，后端会拒绝少于 24 位的 `LOCAL_AI_API_KEY`。

### 阿里云手机验证码

手机号登录/注册使用阿里云短信签名“redacted”和模板
`redacted`，模板参数必须为 `${code}`。开发与测试环境在根目录
`.env` 中填入专用 RAM 用户的密钥：

```env
SMS_ACCESS_KEY_ID=请填写RAM用户AccessKeyId
SMS_ACCESS_KEY_SECRET=请填写RAM用户AccessKeySecret
SMS_SIGN_NAME=redacted
SMS_TEMPLATE_CODE=redacted
```

生产环境将同样的配置写入服务器 `.env.production`，且不得将真实密钥
提交到 Git。RAM 用户建议仅授予 `dysms:SendSms` 权限。当前仅接受中国
大陆 11 位手机号；验证码默认 5 分钟有效、60 秒后可重发，并有每小时/
每日发送上限和输错次数保护。

### 2. 启动基础应用和本地模型

```bash
docker compose --profile local-ai up -d --build
```

首次启动会从模型仓库下载真实模型权重，Embedding、Reranker 和 ASR 健康检查可能需要数分钟才能变为 healthy。查看状态：

```bash
docker compose --profile local-ai ps
docker compose logs -f local-embedding local-reranker local-asr local-ocr
```

访问地址：

| 服务 | 地址 |
| --- | --- |
| Desktop 前端 | http://localhost:5273 |
| 运营后台前端 | http://localhost:5274/admin.html |
| 后端 API | http://localhost:8000 |
| OpenAPI | http://localhost:8000/docs |
| MinIO Console | http://localhost:9001 |
| Embedding 健康检查 | http://localhost:8001/health |
| Reranker 健康检查 | http://localhost:8002/health |
| ASR 健康检查 | http://localhost:8003/health |
| OCR 健康检查 | http://localhost:8004/health |

### 3. 只启动基础应用

如果暂时不下载本地模型：

```bash
docker compose up -d --build
```

同时在 `.env` 中明确关闭对应 Provider：

```env
AI_EMBEDDING_PROVIDER=disabled
AI_RERANK_PROVIDER=disabled
AI_ASR_PROVIDER=disabled
AI_OCR_PROVIDER=disabled
```

此时视频仍可完成 FFmpeg 元数据读取、镜头切分、缩略图和人工剪辑，但没有转写、OCR 和语义搜索。系统会展示真实降级状态，不生成占位结果。

### 4. 运营后台常用命令

运营后台使用独立 Vite 入口。安装过前端依赖后，在一个单独终端中启动：

```bash
cd frontend
npm run dev:admin
```

访问 http://localhost:5274/admin.html。开发态必须使用独立的 `admin.html` 入口；生产后台网关会将根路径自动回退到该入口。生产构建输出到 `frontend/dist-admin/`：

```bash
cd frontend
npm run build:admin
```

管理员账号由后端维护脚本单独管理，不复用普通用户账号。以下命令均在项目根目录执行。

创建管理员；密码通过交互方式输入，至少 12 位，成功后会在本地终端显示 TOTP 二维码：

```bash
docker compose exec backend python scripts/manage_admin.py create \
  --email admin@example.com \
  --name "初始管理员" \
  --role super_admin
```

查看管理员列表：

```bash
docker compose exec -T backend python scripts/manage_admin.py list
```

重置 MFA；会生成新的 TOTP 密钥和二维码，同时撤销该管理员现有会话：

```bash
docker compose exec backend python scripts/manage_admin.py reset-mfa \
  --email admin@example.com
```

停用管理员；会立即撤销其现有会话并阻止再次登录：

```bash
docker compose exec -T backend python scripts/manage_admin.py disable \
  --email admin@example.com
```

创建管理员和重置 MFA 时不要给 `docker compose exec` 添加 `-T`，交互终端用于安全读取密码和稳定显示黑白二维码。二维码、TOTP 密钥和 Authenticator URI 包含同一高敏感凭证，不要发送到聊天、邮件或在线二维码服务。管理员登录异常时可查看后端日志：

```bash
docker compose logs -f backend
```

## 常用 Make 命令

项目根目录的 `Makefile` 封装了 Docker 优先的启动、日志、检查、数据库和维护命令。先查看完整列表：

```bash
make help
```

常用入口：

```bash
make up                 # 启动基础应用
make up-ai              # 启动基础应用和本地 AI
make check              # Compose、后端测试/编译、前端 lint/build
make restart-worker     # 后端任务代码修改后重启 Celery Worker
make logs-worker        # 持续查看 Worker 日志
make frontend-install   # package-lock 变化后修复前端容器依赖
```

创建测试账号（仅开发/测试环境；账号已存在时默认不会改密码）：

```bash
make create-test-account \
  EMAIL=test@example.com \
  PASSWORD='TestPassword123!' \
  NAME='测试账号'
```

如需显式更新已存在账号的密码，增加 `RESET_PASSWORD=1`。重置指定账号的 AI 生图和 AI 生视频已用次数，需要显式确认：

```bash
make reset-ai-usage EMAIL=test@example.com CONFIRM=1
```

该重置只修改 `ai_image_used` 和 `ai_video_used`，不会改变处理时长、存储、导出次数、账期或会员配额；正在排队/执行的 AI 任务也不会被取消。两个账号维护命令在生产环境中都会拒绝执行。

## 非 Docker 开发

基础设施可以使用 Compose：

```bash
docker compose up -d db redis minio
```

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Celery Worker 和 Beat：

```bash
cd backend
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
celery -A app.tasks.celery_app beat --loglevel=info
```

前端：

```bash
cd frontend
npm install
npm run dev
```

本地 AI 可以使用 Compose 单独启动：

```bash
docker compose --profile local-ai up -d --build \
  local-embedding local-reranker local-asr local-ocr
```

非 Docker 后端通过 `.env` 中的 `http://localhost:8001` 至 `8004` 调用这些服务。

## Provider 配置

推荐配置：

```env
AI_EMBEDDING_PROVIDER=local
AI_RERANK_PROVIDER=local
AI_ASR_PROVIDER=local
AI_OCR_PROVIDER=local

AI_TEXT_PROVIDER=dashscope
AI_IMAGE_PROVIDER=dashscope
AI_TEXT_TO_VIDEO_PROVIDER=dashscope
AI_IMAGE_TO_VIDEO_PROVIDER=dashscope
AI_EFFECT_VIDEO_PROVIDER=dashscope
```

基础能力允许的 Provider：

- Embedding：`local` / `dashscope` / `disabled`
- Reranker：`local` / `disabled`
- ASR：`local` / `dashscope` / `disabled`
- OCR：`local` / `dashscope` / `disabled`

生成式能力当前允许：

- 文本、生图、文生视频、图生视频、特效视频：`dashscope` / `disabled`

系统不做隐式回退。如果需要从本地切换线上，必须修改 Provider 并重启 API/Worker。

Compose 中 API、Worker 和 Beat 固定使用 `openvma-docker` 队列；非 Docker 开发默认使用 `openvma-local`。不要让宿主机开发 Worker 与容器 Worker监听同一队列。该隔离可以避免遗留 Worker 因代码版本较旧而截走并丢弃新任务。

## Embedding 迁移与重建

数据库向量字段固定为 1024 维。`BGE-M3` 和 `text-embedding-v3` 虽然都可以输出 1024 维，但它们属于不同向量空间，不能混合搜索。

迁移 `010_embedding_provenance` 为每个 Clip 增加：

- `embedding_model`
- `embedding_dimensions`
- `embedding_version`
- `embedding_status`
- `embedding_source_hash`
- `embedding_updated_at`

升级数据库：

```bash
cd backend
python -m alembic upgrade head
```

本地 Embedding 服务 healthy 后，重建历史向量：

```bash
cd backend
python scripts/reindex_embeddings.py
```

先验证少量记录：

```bash
python scripts/reindex_embeddings.py --limit 20
```

强制重算当前模型的全部记录：

```bash
python scripts/reindex_embeddings.py --all
```

脚本只会把真实模型返回的向量写入数据库；失败记录标记为 `failed`，不会填充零向量或随机向量。

## 素材处理流程

视频素材：

```text
真实文件上传 MinIO
  → Magic Bytes / FFprobe 校验
  → 下载到 Worker 临时目录
  → FFmpeg 提取元数据
  → 本地提取 16kHz WAV
  → FunASR 真实转写
  → FFmpeg 每 10 秒抽帧
  → 本地 PP-OCR 识别并按镜头时间归属
  → FFmpeg Scene Detection 切分镜头
  → 生成真实缩略图和 Clip
  → BGE-M3 建立 1024 维索引
  → 写入 PostgreSQL/pgvector
```

音频素材：

```text
真实音频上传 MinIO
  → Magic Bytes / FFprobe 校验
  → 提取时长、编码、采样率、声道和码率
  → FFmpeg 标准化为 AAC-LC / 48kHz / 双声道 M4A 试听文件
  → 原始文件与试听文件分别持久化
  → 写入素材库和项目媒体索引
```

剪辑工作区支持将独立音频素材加入音频轨，也可以从带音轨的视频中“仅添加音频”或“分离音频”。音频片段支持移动、裁剪、分割、删除、音量、静音、降噪和淡入淡出；浏览器预览会同步播放独立音频轨，最终参数由 FFmpeg 写入导出成片。

某个 AI 基础阶段失败不会把真实媒体处理伪装成失败或成功：FFmpeg 能完成的镜头切分和人工剪辑仍然保留，语义能力会明确显示不可用。

## AI 初剪流程

```text
脚本分镜真实文本
  → 当前 Embedding Provider
  → pgvector 召回真实 Clip
  → 可选 BGE Reranker
  → 相似度阈值判断
  → 后端确定性装配真实时间线
  → 未匹配分镜标记为“待补齐”
```

AI 初剪不会把“待补齐”镜头假装成已经生成。用户可以在分镜中单独创建真实生图或图生视频任务，等第三方成功返回、文件持久化到自有 MinIO 后再加入时间线。

初剪项目内部会保存一份与任务绑定的脚本快照，用于保证异步任务执行期间输入稳定。该记录不是用户新建脚本，不在脚本中心列表和搜索结果中展示；`parent_script_id` 保留与原脚本的追溯关系。对于同一来源脚本，已有“AI 初剪生成中”的项目和运行中 Job 时，接口会复用现有任务，避免重复点击产生多个项目。

## DashScope 配置

```env
DASHSCOPE_API_KEY=
AI_TEXT_MODEL=qwen-plus
AI_IMAGE_MODEL=wanx2.1-t2i-turbo
AI_TEXT_TO_VIDEO_MODEL=wanx2.1-t2v-turbo
AI_IMAGE_TO_VIDEO_MODEL=wan2.7-i2v-2026-04-25
AI_EFFECT_VIDEO_MODEL=wan2.7-i2v-2026-04-25
# AI 配音必须独立显式启用；默认关闭以避免意外产生语音费用
AI_TTS_PROVIDER=disabled
AI_TTS_MODEL=qwen-audio-3.0-tts-flash
AI_TTS_VOICE=longanfengyue
AI_TTS_LANGUAGE=Chinese
AI_TTS_REQUEST_TIMEOUT_SECONDS=120
AI_TTS_DOWNLOAD_TIMEOUT_SECONDS=120
AI_VIDEO_RESOLUTION=720P
AI_VIDEO_DURATION_SECONDS=5
AI_VIDEO_PROMPT_EXTEND=true
AI_VIDEO_WATERMARK=false
DASHSCOPE_POLL_INTERVAL_SECONDS=2
DASHSCOPE_GENERATION_TIMEOUT_SECONDS=600
```

启用字幕 AI 配音时，将 `AI_TTS_PROVIDER` 改为 `dashscope`。工作台会按场景去重并切分字幕，逐段调用千问非实时 TTS，将真实结果标准化为 48kHz WAV 后保存到 MinIO，最后拼成项目旁白母带并写入现有 `global_audio.voiceAssetId`。字幕改变只会将对应配音显示为过期，不会自动再次产生费用。默认模型 `qwen-audio-3.0-tts-flash` 的系统音色必须使用其兼容音色，例如 `longanfengyue`；`Cherry` 等音色仅用于 Qwen3-TTS 系列，不能混用。

`wan2.7-i2v-2026-04-25` 已使用当前中国内地 DashScope 账号完成模型权限探测。图生视频和 AI 草图视频使用两个独立配置项，当前显式指向同一模型；以后可单独替换草图视频模型，不影响普通图生视频。

图片和视频生成不使用 OpenAI-compatible 的 `/compatible-mode/v1/images/generations`。当前 Provider 按 DashScope 原生异步协议执行：

```text
生图提交：POST /api/v1/services/aigc/text2image/image-synthesis
视频提交：POST /api/v1/services/aigc/video-generation/video-synthesis
任务查询：GET  /api/v1/tasks/{task_id}
请求头：    X-DashScope-Async: enable
```

万相 2.7 的首帧输入使用 `input.media=[{type:first_frame,url:...}]`，不再使用旧版 `img_url`。OpenVMA 私有 MinIO 和浏览器 Canvas 不能直接被云端读取，因此 Worker 会先获取 `/api/v1/uploads?action=getPolicy` 临时凭证，将图片上传到百炼临时 OSS，再以 `oss://` 地址提交任务，并添加 `X-DashScope-OssResourceResolve: enable`。第三方生成结果成功后仍会转存回 OpenVMA 自有 MinIO。

Provider 只轮询当前配置模型返回的 `task_id`，直到真实成功、失败或超时；不会因为 404、额度不足或模型无权限而静默切换到另一个付费模型。成功媒体必须下载、校验并持久化到 MinIO 后，业务 Job 才能进入 `SUCCEEDED`。

上线前必须分别完成：

1. 文本 JSON 生成测试。
2. 生图并转存 MinIO 测试。
3. 文生视频并转存 MinIO 测试。
4. 图生视频并转存 MinIO 测试。
5. 参考图/运动控制特效测试。
6. 并发、限流、超时、费用和临时 URL 域名测试。

额度较少时，优先运行 `backend/tests/test_ai_provider.py` 的 Mock 合约测试；真实冒烟测试每种生成能力只执行一次，并记录模型、地域、任务 ID 和供应商返回的真实错误。不要用批量分镜测试验证第三方接口连通性。

## 测试与校验

每次提交前推荐在项目根目录运行：

```bash
make check
```

该命令会执行 Compose 配置检查、后端单元测试、Python 编译检查、前端 ESLint 和生产构建。GitHub Actions 也会对 Push 和 Pull Request 执行对应的轻量检查。

后端单元测试：

```bash
cd backend
python -m unittest discover -s tests -v
```

Python 编译检查：

```bash
python -m compileall -q backend/app backend/tests backend/scripts local-ai
```

前端类型检查与构建：

```bash
cd frontend
npx tsc --noEmit
npm run build
```

Docker Compose 配置检查：

```bash
docker compose config --quiet
```

当前已有单元测试和真实 API/浏览器回归，但仍需补充完整 API 集成测试、Playwright CI、压力测试和大文件测试。

## 生产安全要求

生产环境至少需要：

```env
ENVIRONMENT=production
JWT_SECRET=至少32位随机字符串
CORS_ORIGINS=https://明确的前端域名
TRUSTED_HOSTS=明确的API域名
RATE_LIMIT_ENABLED=true
MINIO_PUBLIC_ENDPOINT=公网媒体域名
MINIO_PUBLIC_SECURE=true
LOCAL_AI_API_KEY=至少24位随机字符串
```

本地 AI 服务应仅暴露在内部网络。Compose 的模型端口默认绑定 `127.0.0.1`；生产部署建议取消宿主机端口映射，只允许 Backend/Celery 所在网络访问。

## 尚需外部凭证或服务

- DashScope：高质量脚本、生图、文生视频、图生视频、特效视频的真实成功链路。
- 支付宝：会员升级和支付回调。
- 阿里云短信：手机验证码。
- 微信开放平台：微信扫码登录。
- 邀请邮件 Provider：当前使用真实邀请链接，不伪造邮件发送成功。
- 正式税务电子发票服务：当前只生成真实开票申请单 PDF，不是电子发票。
- 正版背景音乐服务、文案润色和 TTS 产品入口仍需按真实 Provider 接入。

## 设计资料

本地 Wiki、原型上传文件、测试视频和废弃设计资料体积较大且可能包含内部内容，因此不纳入代码仓库。需要共享的稳定设计说明应经过整理后单独放入轻量的 `docs/` 目录；原型中的静态数据、定时任务和交互演示只用于表达界面，不允许直接复制为正式业务实现。
