# OpenVMA 生产部署手册

生产链路固定为：公网用户 → 雷池 SafeLine → OpenVMA 内部 Nginx → FastAPI / React / MinIO。PostgreSQL、Redis、Backend、MinIO Console 和本地 AI 服务均不直接暴露公网。

## 1. 服务器准备

建议将雷池与业务目录分开：

```text
/data/safeline       雷池官方安装目录
/srv/openvma         OpenVMA 代码与生产配置
/srv/openvma/backups 数据备份（建议再同步到异机或对象存储）
```

服务器需要 Docker Engine、Docker Compose v2、Git、curl，并开放公网 80/443 给雷池。OpenVMA 网关默认只监听 `127.0.0.1:8080`；如果雷池容器无法访问宿主机回环地址，请改成服务器内网 IP，并通过云安全组或主机防火墙只允许雷池访问该端口。

## 2. 创建生产配置

```bash
cd /srv/openvma
cp .env.production.example .env.production
chmod 600 .env.production
```

至少替换以下值：

- `APP_DOMAIN`、`MEDIA_DOMAIN`、`CORS_ORIGINS`、`TRUSTED_HOSTS`
- `POSTGRES_PASSWORD` 和对应 `DATABASE_URL`
- `REDIS_PASSWORD` 和对应 `REDIS_URL`
- `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_PUBLIC_ENDPOINT`
- `JWT_SECRET`
- 实际启用的 AI、微信、短信、支付宝凭证

密码建议使用 `openssl rand -hex 24` 或更长的十六进制字符串。这样写入 `DATABASE_URL`、`REDIS_URL` 时不需要额外 URL 编码。不要把真实 `.env.production` 提交到 Git。

初次上线建议保持所有 AI Provider 为 `disabled`，先验证基础业务链路；随后再逐项启用并进行真实模型冒烟测试。启用本地 AI 时，将相应 Provider 改成 `local`，设置至少 24 位的 `LOCAL_AI_API_KEY`，并按“本地 AI”一节启动服务。

## 3. 首次发布

每次发布都必须使用不可变镜像标签，推荐 Git commit SHA：

```bash
cd /srv/openvma
export OPENVMA_ENV_FILE=/srv/openvma/.env.production
export OPENVMA_IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
./deploy/deploy.sh
```

脚本会依次执行：配置校验、已有环境备份、构建带版本标签的镜像、启动 PostgreSQL/Redis/MinIO、创建 bucket、执行一次性 Alembic 迁移、更新 API/Worker/Beat/Gateway，以及内部健康检查。首次部署没有旧数据库容器时会明确跳过备份。

发布后查看状态：

```bash
docker compose -f compose.prod.yml --env-file .env.production ps
docker compose -f compose.prod.yml --env-file .env.production logs -f backend celery-worker gateway
```

## 4. 配置雷池

按照 [safeline.md](safeline.md) 创建应用域名和媒体域名、配置证书、上游、WebSocket 与来源 IP。雷池配置完成后运行公网检查：

```bash
OPENVMA_ENV_FILE=/srv/openvma/.env.production \
OPENVMA_PUBLIC_CHECK=1 \
./deploy/healthcheck.sh
```

## 5. 本地 AI（可选）

首次模型下载时间和资源占用较大。基础系统健康后再执行：

```bash
docker compose \
  -f compose.prod.yml \
  --env-file .env.production \
  --profile local-ai \
  up -d --build local-embedding local-reranker local-asr local-ocr
```

确认四个服务健康后，将对应 Provider 改成 `local`，再以新的不可变版本标签重新运行 `deploy.sh`，使 Backend 和 Worker 读取新配置。CPU 可以运行，但长视频处理会较慢；生产并发初始保持 `CELERY_WORKER_CONCURRENCY=1`。

## 6. 备份与保留

手动备份：

```bash
OPENVMA_ENV_FILE=/srv/openvma/.env.production ./deploy/backup.sh
```

每个备份目录包含 PostgreSQL custom-format dump、MinIO bucket 镜像、manifest，以及 Linux 环境下的 SHA256 校验文件。在线备份中的 PostgreSQL dump 自身一致，但数据库与 MinIO mirror 之间不是跨服务原子快照；关键发布或灾难恢复前应进入维护窗口、停止写入后再备份。至少保留日备份、周备份和一个异机副本；只存在同一服务器磁盘上的备份不能覆盖磁盘或整机故障。

建议通过 cron 或 systemd timer 定时调用脚本，但不要把密钥写进 crontab；只传入受限权限的环境文件路径。

## 7. 回滚

应用回滚不会自动执行 Alembic downgrade。只有确认旧版本兼容当前数据库 schema 时才能运行：

```bash
OPENVMA_ENV_FILE=/srv/openvma/.env.production \
ROLLBACK_IMAGE_TAG=<previous-commit-tag> \
CONFIRM_SCHEMA_COMPATIBLE=1 \
./deploy/rollback.sh
```

脚本先备份当前数据，再切换 Backend、Worker、Beat 和 Gateway 镜像并执行健康检查。若变更包含不向后兼容的数据库迁移，应先停止写入并按 [restore.md](restore.md) 的人工流程恢复数据库和对象存储，不能只回滚镜像。

## 8. 上线验收清单

- 雷池公网只开放 80/443，内部 8080 不对公网开放。
- `/api/health/live` 与 `/api/health/ready` 均返回 200。
- 未登录 API、登录、刷新 Token、退出流程正常。
- WebSocket 连接收到 `auth_ok`，任务进度可以更新；轮询仍可作为兜底。
- 上传有效小文件、接近 1 GiB 的有效文件以及超过 1 GiB 的文件；超过限制必须返回 413。
- 媒体域名支持签名 URL、Range 请求和视频拖动播放。
- Worker 并发为 1，数据库连接数、CPU、内存、磁盘和任务积压处于预期范围。
- 备份完成，并在隔离环境至少成功演练一次恢复。
- API 文档在生产环境不可访问，PostgreSQL、Redis、MinIO Console 无公网端口。
