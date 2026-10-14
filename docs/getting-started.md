# 快速开始

[返回 README](../README.md) · [配置](configuration.md) · [开发](development.md)

先用自己的短视频完成上传、人工编辑和 MP4 导出，再按需启用 AI。根目录 `docker-compose.yml` 用于受控本地开发，生产环境使用 [生产模板与操作手册](../deploy/README.md)。

## Docker 基础启动

安装 Docker Engine/Desktop 和 Compose v2。在项目根目录执行：

```bash
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

已有 `.env` 时保留它，先检查所有 `AI_*_PROVIDER` 为 `disabled`。新示例已关闭全部 AI，不需要短信、微信或云端模型密钥，也不会启动 `local-ai` profile。应用镜像构建仍需下载软件依赖。

API 容器启动时执行 `alembic upgrade head`。素材 bucket 在存储客户端首次使用时创建。查看日志与健康状态：

```bash
docker compose logs -f backend celery-worker celery-beat
curl --fail --show-error http://localhost:8000/api/health
```

前端在 [localhost:5273](http://localhost:5273)，API 文档在 [localhost:8000/docs](http://localhost:8000/docs)。MinIO Console 在 [localhost:9001](http://localhost:9001)，开发凭证见 Compose。媒体访问地址必须能被浏览器访问，不能使用容器内部主机名。

## 第一次媒体流程

1. 打开前端，选择邮箱注册，填写姓名、有效邮箱和至少 6 位密码。邮箱密码注册无需短信服务；开发环境也不会提供固定验证码。
2. 创建空白项目，或从上传素材入口创建项目。
3. 上传自己有使用权的几秒视频。等待真实处理任务完成，确认缩略图与播放正常。
4. 建立场景与镜头，填写台词/画面描述，选择上传的素材并调整素材区间和镜头时长。
5. 编排主成片，检查预览、字幕与音轨；未选择素材的镜头需要补齐。
6. 导出主成片为 MP4，等待任务成功后播放或下载产物。

这条流程不需要 AI。模型关闭时转写、OCR、视觉识别、语义匹配、自动脚本和生成媒体不可用；FFmpeg 元数据、镜头切分、缩略图和人工编辑仍保留。普通用户不是运营管理员。

## 可选本地 AI

先编辑根目录 `.env`，只启用需要的能力：

```dotenv
AI_EMBEDDING_PROVIDER=local
AI_RERANK_PROVIDER=local
AI_ASR_PROVIDER=local
AI_OCR_PROVIDER=local
LOCAL_AI_API_KEY=replace-with-a-random-token-at-least-24-characters
```

再执行：

```bash
docker compose --profile local-ai up -d --build
docker compose --profile local-ai ps
docker compose logs -f local-embedding local-reranker local-asr local-ocr
```

首次会下载真实模型权重。等待健康检查通过再处理媒体；历史素材需重建向量时见 [开发指南](development.md)。本地服务健康地址为 `http://localhost:8001/health` 至 `8004/health`。服务启用后端口仅绑定本机。

`--profile local-ai` 只控制服务启动，不会自动把 `.env` 中的 Provider 改成 `local`。改环境变量后使用 `up -d` 重新创建受影响服务；单纯 `restart` 不会更新容器环境。

云端生成、文本/视觉和 TTS 见 [配置矩阵](configuration.md)，启用前确认服务权限和费用。

## 宿主机开发

需要 Node 22、Python 3.12、FFmpeg/FFprobe。先在根目录创建 `.env`，其中数据库、Redis、MinIO 与本地 AI URL 使用宿主机地址。基础设施仍可用 Docker：

```bash
docker compose up -d db redis minio
```

API 终端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API、Alembic、Worker 的 Settings 读取仓库根 `.env`，不依赖启动时的工作目录；进程环境变量覆盖文件配置。Docker 中服务连接地址由 Compose 覆盖为内部地址。

另外两个终端分别启动 Worker 和 Beat，均从 `backend/` 执行并激活同一虚拟环境：

```bash
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4 \
  --queues=openvma-local,openvma-local.control,openvma-local.short-ai,openvma-local.video,openvma-local.media,openvma-local.export
```

```bash
celery -A app.tasks.celery_app beat --loglevel=info \
  --schedule=/tmp/openvma-local-celerybeat-schedule
```

上述队列名对应默认 `CELERY_TASK_DEFAULT_QUEUE=openvma-local`；若修改基名或显式队列配置，须同步 `--queues`。容器使用 `openvma-docker` 及其后缀队列，宿主机 Worker 不应监听容器队列。只监听默认队列会漏掉媒体、匹配、视频与导出任务。参见 [Celery 路由](../backend/app/tasks/celery_app.py)。

前端终端：

```bash
cd frontend
npm ci
npm run dev
```

宿主机 Vite 默认代理到 `http://localhost:8000`。连接其他 API 时使用服务端变量：

```bash
API_PROXY_TARGET=http://localhost:8000 npm run dev
```

Compose 前端使用 `http://backend:8000`。浏览器继续使用同源 `/api` 请求，详见 [Vite 配置](../frontend/vite.config.ts)。

## 独立运营后台

开发 Compose 运行普通 Vite 服务，它也能直接访问 `/admin.html`。管理端开发建议使用独立端口；生产隔离依靠独立构建和网关配置。安装前端依赖后，在另一终端执行：

```bash
cd frontend
npm run dev:admin
```

访问 [localhost:5274/admin.html](http://localhost:5274/admin.html)。首次管理员由后端脚本创建，密码交互输入且至少 12 位：

```bash
docker compose exec backend python scripts/manage_admin.py create \
  --email admin@example.com --name "初始管理员" --role super_admin
```

宿主机 API 模式下，在 `backend/` 的虚拟环境中运行同样的 `python scripts/manage_admin.py create ...`。创建和重置 MFA 命令保留交互终端，不加 `-T`。TOTP 密钥和二维码只在自己的终端/Authenticator 中使用。其他后台操作见 [生产部署手册](../deploy/README.md)。

## 排查启动问题

| 现象 | 检查 |
| --- | --- |
| 前端 API 502 | API 是否启动；Compose Vite 目标是否为 `backend:8000`；宿主机是否为 `localhost:8000` |
| 注册失败 | 查看可见错误和 API 日志；邮箱格式、密码长度、邮箱重复、数据库迁移 |
| 任务一直排队 | Worker/Beat 日志；API 和 Worker 的 Redis、队列基名与后缀是否一致 |
| 素材播放失败 | `MINIO_PUBLIC_ENDPOINT` 是否浏览器可达，协议与签名 URL 是否一致 |
| AI 不可用 | Provider 是否显式启用，密钥/模型权限或本地健康状态 |
| 配置修改未生效 | 重新创建容器或重启宿主机进程；`get_settings()` 在进程内缓存 |

停止本地服务可用 `docker compose down`，默认保留数据卷。不要为排查普通问题删除数据卷；生产维护使用独立部署流程。
