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

- `APP_DOMAIN`、`ADMIN_DOMAIN`、`MEDIA_DOMAIN`、`CORS_ORIGINS`、`TRUSTED_HOSTS`
- `POSTGRES_PASSWORD` 和对应 `DATABASE_URL`
- `REDIS_PASSWORD` 和对应 `REDIS_URL`
- `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_PUBLIC_ENDPOINT`
- `JWT_SECRET`、与其不同的 `ADMIN_JWT_SECRET`、`ADMIN_MFA_ENCRYPTION_KEY`
- `HOST_METRICS_PATH`；应指向 OpenVMA 数据所在磁盘上的专用空目录
- 实际启用的 AI、微信、短信、支付宝凭证

密码建议使用 `openssl rand -hex 24` 或更长的十六进制字符串。这样写入 `DATABASE_URL`、`REDIS_URL` 时不需要额外 URL 编码。不要把真实 `.env.production` 提交到 Git。

服务器资源指标每小时采集一次，并支持后台手动刷新。首次部署前创建专用空目录；后台只通过该目录读取所在文件系统的容量，不挂载宿主机根目录，也不接入 Docker Socket：

```bash
mkdir -p /srv/openvma/.host-metrics
chmod 755 /srv/openvma/.host-metrics
```

对应生产配置为：

```dotenv
HOST_METRICS_PATH=/srv/openvma/.host-metrics
SYSTEM_METRICS_DISK_PATH=/host-metrics-disk
SYSTEM_METRICS_SCOPE=host
SYSTEM_METRICS_RETENTION_DAYS=30
```

如果 MinIO 以后迁移到独立数据盘，应把 `HOST_METRICS_PATH` 改为该数据盘上的专用空目录。每小时快照用于运营概览，不替代秒级 Prometheus、云监控或故障告警。

初次上线建议保持所有 AI Provider 为 `disabled`，先验证基础业务链路；随后再逐项启用并进行真实模型冒烟测试。启用本地 AI 时，将相应 Provider 改成 `local`，设置至少 24 位的 `LOCAL_AI_API_KEY`，并按“本地 AI”一节启动服务。

## 3. 首次发布

首次发布完成后的日常版本更新、独立版本目录、发布前任务检查、本地 AI 更新和镜像回滚流程，统一参见 [版本发布与回滚运行手册](release.md)。

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
docker compose -f compose.prod.yml --env-file .env.production logs -f backend celery-worker gateway admin-gateway
```

首次发布并完成迁移后，以交互方式创建第一个管理员。密码至少 12 位，命令会在本地终端显示仅供 Authenticator 扫描的二维码，并只展示一次 TOTP 密钥和 Authenticator URI：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  exec backend python scripts/manage_admin.py create \
  --email admin@example.com --name "初始管理员" --role super_admin
```

生产管理员常用维护命令如下。创建管理员和重置 MFA 时必须保留交互终端，不要添加 `-T`。

查看管理员列表：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  exec -T backend python scripts/manage_admin.py list
```

重置 MFA；会显示新的本地二维码、废止旧 TOTP 并撤销该管理员现有会话：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  exec backend python scripts/manage_admin.py reset-mfa \
  --email admin@example.com
```

停用管理员；会立即撤销该管理员现有会话：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  exec -T backend python scripts/manage_admin.py disable \
  --email admin@example.com
```

查看后台网关和管理员认证日志：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  logs -f admin-gateway backend
```

二维码、TOTP 密钥和 Authenticator URI 包含同一高敏感凭证，不得进入工单、聊天、邮件、截图共享或在线二维码服务。管理员角色固定为 `super_admin`、`operator` 和 `finance`；新增账号应按最小权限原则选择角色。

当前确认的生产后台域名为 `admin.example.com`。MVP 阶段采用公网开放策略，不配置 VPN 或固定出口 IP 白名单；雷池 HTTPS、WAF、CC/Bot 防护，以及生产环境 Redis 认证接口限流必须保持启用。管理员登录仍强制使用独立账号、TOTP MFA，连续 5 次失败锁定 15 分钟。域名与路径不可作为安全边界，后续具备条件时应升级为 VPN 或固定出口 IP 白名单。

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

每个备份目录包含 PostgreSQL custom-format dump、MinIO bucket 镜像、manifest，以及 Linux 环境下的 SHA256 校验文件。发布脚本创建的 manifest 会分别记录 `source_image_tag` 和 `target_image_tag`，避免把迁移前数据误标为目标版本。在线备份中的 PostgreSQL dump 自身一致，但数据库与 MinIO mirror 之间不是跨服务原子快照；关键发布或灾难恢复前应进入维护窗口、停止写入后再备份。至少保留日备份、周备份和一个异机副本；只存在同一服务器磁盘上的备份不能覆盖磁盘或整机故障。

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

- 雷池公网只开放 80/443，内部 8080/8081 不对公网开放。
- `/api/health/live` 与 `/api/health/ready` 均返回 200。
- 未登录 API、登录、刷新 Token、退出流程正常。
- WebSocket 连接收到 `auth_ok`，任务进度可以更新；轮询仍可作为兜底。
- 上传有效小文件、接近 1 GiB 的有效文件以及超过 1 GiB 的文件；超过限制必须返回 413。
- 媒体域名支持签名 URL、Range 请求和视频拖动播放。
- Worker 并发为 1，数据库连接数、CPU、内存、磁盘和任务积压处于预期范围。
- 备份完成，并在隔离环境至少成功演练一次恢复。
- API 文档在生产环境不可访问，PostgreSQL、Redis、MinIO Console 无公网端口。
- 用户域名访问 `/api/admin/*` 和 `/admin.html` 返回 404；后台域名访问普通 `/api/*` 返回 404。
