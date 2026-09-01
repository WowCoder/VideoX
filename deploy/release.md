# OpenVMA 版本发布与回滚运行手册

本文档用于已经完成首次部署后的日常版本发布。首次安装、生产环境变量、雷池接入和灾难恢复分别参见：

- [生产部署手册](README.md)
- [雷池 SafeLine 配置说明](safeline.md)
- [恢复演练与灾难恢复](restore.md)

## 1. 发布原则

- 只发布已经提交到 Git 的代码，不发布工作区中的临时文件。
- 使用 Git commit SHA 作为不可变镜像标签，生产环境禁止使用 `latest`。
- 服务器上的 `.env.production`、备份、数据卷和入口配置不随代码包覆盖。
- 发布前检查长任务并创建备份；发布后同时验证内部健康状态和真实业务链路。
- PostgreSQL、Redis、MinIO 和本地 AI 不因普通前后端发布而停止或重建。
- 不执行 `docker compose down -v`；不要在回滚窗口内执行 `docker image prune -a`。
- 应用回滚不会自动执行 Alembic downgrade。数据库迁移不兼容时必须走人工恢复流程。

当前推荐使用“本地生成 Git 归档、服务器解压到独立版本目录”的交付方式。它不要求生产服务器持有 GitHub 凭证，也适用于服务器现有代码目录不是 Git 工作区的情况。

## 2. 目录约定

推荐生产服务器使用以下结构：

```text
/srv/openvma/
├── .env.production          生产密钥和配置，权限 600
├── .deploy-state/           当前版本和上一个版本
├── backups/                 PostgreSQL 与 MinIO 备份
├── releases/                每次发布的只读代码快照
│   ├── <commit-sha>/
│   └── <commit-sha>/
├── ip-access/               可选的临时 IP HTTPS 入口，不随应用发布覆盖
└── temporary-access/        可选的临时访问保护，不随应用发布覆盖
```

Docker Compose 项目名固定为 `openvma-production`，因此从不同版本目录运行 `compose.prod.yml` 时仍会复用同一组生产网络和数据卷。

## 3. 发布窗口前检查

普通发布会重新创建 Backend、Celery Worker、Celery Beat 和 Gateway。当前为单实例部署，切换期间可能出现几秒到几十秒的短暂不可用。

先检查正在处理的任务：

```bash
cd /srv/openvma

docker compose \
  -f compose.prod.yml \
  --env-file .env.production \
  exec -T backend \
  celery -A app.tasks.celery_app inspect active
```

如有视频处理、导出、AI 生成等长任务，优先等待任务结束或选择维护窗口。Worker 被强制重建时，长任务可能中断、重新排队或失败。

检查容器、磁盘和 Docker 空间：

```bash
docker compose \
  -f compose.prod.yml \
  --env-file .env.production \
  --profile local-ai \
  ps

df -h
docker system df
```

发布前至少确认：

- PostgreSQL、Redis、MinIO 和 Backend 为健康状态。
- 磁盘可以同时容纳新旧镜像以及一次完整备份。
- 没有必须等待完成的长任务。
- 新版本的配置项已经在 `.env.production` 中准备好，但没有覆盖现有密钥。
- 数据库迁移已评估向后兼容性和回滚策略。

## 4. 本地验证和生成发布包

### 4.1 备份复用、镜像预检与构建缓存

发布脚本默认会在切换前创建一次 PostgreSQL + MinIO 备份。如果已经在同一发布窗口创建并校验了最终备份，可将其路径传给发布脚本，脚本会校验 manifest、版本标签和 SHA256 后复用，不会再次执行全量备份：

```bash
OPENVMA_BACKUP_PATH=/srv/openvma/backups/<timestamp> \
OPENVMA_IMAGE_TAG=<target-commit-sha> \
./deploy/deploy.sh
```

未提供 `OPENVMA_BACKUP_PATH` 时仍按默认策略自动备份。备份脚本会将 MinIO 增量同步到 `minio-current`，并为每次发布生成可独立恢复的快照目录；未变化对象使用硬链接复用磁盘空间。

生产机默认使用阿里云 apt/PyPI 镜像和 npmmirror npm 镜像，并在构建前做连通性预检。也可以通过 `OPENVMA_APT_MIRROR`、`OPENVMA_PIP_INDEX_URL` 和 `OPENVMA_NPM_REGISTRY` 覆盖。Backend 和 Gateway Dockerfile 使用 BuildKit cache mount，生产机应保持 Docker/BuildKit 缓存，不要在普通发布后清理构建缓存。

数据库迁移默认使用 `OPENVMA_MIGRATION_MODE=auto`：仅当数据库已经处于目标 head 且新旧迁移目录一致时跳过 migration 容器；任何不确定情况都会执行迁移。需要强制执行时使用 `OPENVMA_MIGRATION_MODE=always`。

在开发机仓库中运行完整检查：

```bash
make check
```

确认所有发布内容都已经提交：

```bash
git status --short
```

工作区应为空。然后使用 12 位 commit SHA 生成归档：

```bash
OPENVMA_RELEASE_TAG="$(git rev-parse --short=12 HEAD)"
OPENVMA_RELEASE_ARCHIVE="/tmp/openvma-${OPENVMA_RELEASE_TAG}.tar.gz"

git archive \
  --format=tar.gz \
  --output="${OPENVMA_RELEASE_ARCHIVE}" \
  HEAD

sha256sum "${OPENVMA_RELEASE_ARCHIVE}"
```

macOS 没有 `sha256sum` 时使用：

```bash
shasum -a 256 "${OPENVMA_RELEASE_ARCHIVE}"
```

`git archive` 只包含已提交文件，不包含 `.env.production`、本地 `.env`、Git 历史和未跟踪文件。

## 5. 上传并展开版本目录

从开发机上传归档。服务器地址由运维人员按实际环境填写：

```bash
scp "${OPENVMA_RELEASE_ARCHIVE}" \
  root@<server-ip>:/tmp/
```

登录服务器后设置相同版本号：

```bash
OPENVMA_RELEASE_TAG="<12-character-commit-sha>"
OPENVMA_RELEASE_DIR="/srv/openvma/releases/${OPENVMA_RELEASE_TAG}"
OPENVMA_RELEASE_ARCHIVE="/tmp/openvma-${OPENVMA_RELEASE_TAG}.tar.gz"

install -d -m 0755 "${OPENVMA_RELEASE_DIR}"
tar -xzf "${OPENVMA_RELEASE_ARCHIVE}" -C "${OPENVMA_RELEASE_DIR}"
```

可以对照开发机输出校验归档哈希。确认解压成功后再进入发布步骤。不要把 `/srv/openvma/.env.production` 复制到版本目录，也不要从归档中覆盖它。

## 6. 初始化版本状态

历史环境第一次切换到标准发布流程时，先记录当前正在运行的镜像标签：

```bash
docker compose \
  -f /srv/openvma/compose.prod.yml \
  --env-file /srv/openvma/.env.production \
  images
```

从 Backend 或 Gateway 的 `TAG` 列读取当前标签，然后执行：

```bash
OPENVMA_CURRENT_TAG="<currently-running-tag>"

install -d -m 0700 /srv/openvma/.deploy-state
printf '%s\n' "${OPENVMA_CURRENT_TAG}" \
  > /srv/openvma/.deploy-state/current_tag
```

只需初始化一次。此后 `deploy.sh` 会自动维护：

```text
.deploy-state/current_tag
.deploy-state/previous_tag
```

## 7. 执行主应用发布

在新版本目录运行生产发布脚本：

```bash
cd "${OPENVMA_RELEASE_DIR}"

OPENVMA_ENV_FILE=/srv/openvma/.env.production \
OPENVMA_BACKUP_DIR=/srv/openvma/backups \
OPENVMA_STATE_DIR=/srv/openvma/.deploy-state \
OPENVMA_APT_MIRROR=mirrors.aliyun.com \
OPENVMA_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
OPENVMA_NPM_REGISTRY=https://registry.npmmirror.com \
OPENVMA_IMAGE_TAG="${OPENVMA_RELEASE_TAG}" \
./deploy/deploy.sh
```

如果生产服务器访问 Debian、PyPI 或 npm 官方源不稳定，可以只在构建/发布命令的进程环境中增加镜像源，不需要把它们写入包含业务密钥的环境文件：

```bash
OPENVMA_APT_MIRROR=mirrors.aliyun.com \
OPENVMA_PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
OPENVMA_NPM_REGISTRY=https://registry.npmmirror.com \
OPENVMA_ENV_FILE=/srv/openvma/.env.production \
OPENVMA_BACKUP_DIR=/srv/openvma/backups \
OPENVMA_STATE_DIR=/srv/openvma/.deploy-state \
OPENVMA_IMAGE_TAG="${OPENVMA_RELEASE_TAG}" \
./deploy/deploy.sh
```

脚本按顺序执行：

1. 校验合并后的 Compose 配置。
2. 备份 PostgreSQL 和 MinIO；MinIO 先增量同步到稳定镜像目录，再生成可独立恢复的快照。manifest 的 `source_image_tag` 记录发布前版本，`target_image_tag` 记录本次目标版本。
3. 构建带版本标签的 Backend 和 Gateway 镜像。
4. 确保 PostgreSQL、Redis 和 MinIO 正常运行。
5. 初始化 MinIO bucket。
6. 在数据库已处于目标 head 且迁移目录未变化时跳过 Alembic 容器，否则运行 migration。
7. 重新创建 Backend、Celery Worker 和 Celery Beat。
8. 重新创建内部 Gateway。
9. 执行内部 Nginx、Backend readiness 和 MinIO 健康检查。
10. 更新当前版本和上一个版本记录。

成功结束时会输出：

```text
OpenVMA <commit-sha> 发布完成
```

生产环境不要用开发 Compose 或 Makefile 的开发目标替代上述命令：

```text
make up
make rebuild
make rebuild-ai
docker compose down
docker compose down -v
```

其中 `docker compose down -v` 会删除生产数据卷，禁止执行。

## 8. 本地 AI 更新

普通前端或后端发布不需要重建本地 AI。只有以下代码发生变化时才执行本节：

```text
local-ai/embedding/
local-ai/reranker/
local-ai/asr/
local-ai/ocr/
```

先构建带相同版本标签的 AI 镜像：

```bash
cd "${OPENVMA_RELEASE_DIR}"
export OPENVMA_IMAGE_TAG="${OPENVMA_RELEASE_TAG}"

docker compose \
  -f compose.prod.yml \
  --env-file /srv/openvma/.env.production \
  --profile local-ai \
  build \
  local-embedding \
  local-reranker \
  local-asr \
  local-ocr
```

仅重新创建确实发生变化的服务。例如只修改了 OCR：

```bash
docker compose \
  -f compose.prod.yml \
  --env-file /srv/openvma/.env.production \
  --profile local-ai \
  up -d --no-deps --force-recreate local-ocr
```

如果四个服务都修改，再一起重新创建。模型镜像较大，首次下载和健康检查可能需要数分钟；必须等待容器显示 `healthy`。

## 9. 发布后验证

### 9.1 内部健康检查

```bash
cd "${OPENVMA_RELEASE_DIR}"

OPENVMA_ENV_FILE=/srv/openvma/.env.production \
./deploy/healthcheck.sh
```

检查完整服务状态：

```bash
docker compose \
  -f compose.prod.yml \
  --env-file /srv/openvma/.env.production \
  --profile local-ai \
  ps
```

查看本次发布以来的日志：

```bash
docker compose \
  -f compose.prod.yml \
  --env-file /srv/openvma/.env.production \
  logs --since=15m \
  backend celery-worker celery-beat gateway admin-gateway
```

日志中不应持续出现数据库连接、Redis、MinIO、迁移、Celery 队列或 5xx 错误。

### 9.2 雷池后的公网检查

正式域名和雷池已经启用时执行：

```bash
cd "${OPENVMA_RELEASE_DIR}"

OPENVMA_ENV_FILE=/srv/openvma/.env.production \
OPENVMA_PUBLIC_CHECK=1 \
./deploy/healthcheck.sh
```

健康检查要求接口最终直接返回 HTTP 200，302/307 登录跳转或其他重定向不会被当成成功。公网入口带有独立访问保护时，还必须使用已经通过保护层认证的浏览器或受控测试客户端完成真实业务冒烟；仅看到登录页 200 不能证明应用健康。

### 9.3 真实业务冒烟测试

至少验证：

- 访问保护或雷池可以正常放行授权用户。
- 邮箱登录、Token 刷新和退出正常。
- 工作台、项目、脚本和剪辑页面可以加载。
- 上传一个小型有效媒体文件。
- 媒体签名 URL、Range 请求和视频拖动播放正常。
- WebSocket 收到 `auth_ok`，任务进度持续更新。
- 创建一个低成本测试任务并确认 Worker 完成处理。
- 如果更新了本地 AI，对实际发生变化的模型执行一次真实推理。

临时 IP HTTPS 入口属于独立基础设施层。只要它继续反向代理生产 Gateway，普通应用发布不需要重启临时入口。只有入口 Nginx、访问保护脚本、证书或网络拓扑改变时才单独更新它。

## 10. 应用镜像回滚

先读取版本状态：

```bash
sed -n '1p' /srv/openvma/.deploy-state/current_tag
sed -n '1p' /srv/openvma/.deploy-state/previous_tag
```

只有确认旧版本兼容当前数据库 schema 时，才允许应用回滚：

```bash
cd "${OPENVMA_RELEASE_DIR}"

OPENVMA_ENV_FILE=/srv/openvma/.env.production \
OPENVMA_BACKUP_DIR=/srv/openvma/backups \
OPENVMA_STATE_DIR=/srv/openvma/.deploy-state \
ROLLBACK_IMAGE_TAG="<previous-image-tag>" \
CONFIRM_SCHEMA_COMPATIBLE=1 \
./deploy/rollback.sh
```

回滚脚本会先备份当前数据，再切换 Backend、Worker、Beat 和 Gateway 镜像，并执行内部健康检查。它不会回退数据库 schema。

以下情况不能只回滚镜像：

- 新版本删除或重命名了旧版本依赖的表、列或约束。
- 数据迁移已不可逆地改写业务数据。
- 对象存储路径或数据格式发生不兼容改变。
- 旧 Worker 无法识别新版本已经进入队列的任务载荷。

遇到上述情况，应先停止写入并按照 [恢复演练与灾难恢复](restore.md) 在隔离目标验证备份，再决定数据库、对象存储和应用版本的整体恢复方案。

## 11. 发布完成记录

每次发布至少记录：

- Git commit SHA 和提交说明。
- 发布开始、结束时间和操作人。
- 发布前备份目录。
- 数据库迁移版本。
- 更新的应用服务和本地 AI 服务。
- 内部健康检查、外部健康检查和业务冒烟测试结果。
- 当前可回滚镜像标签。
- 发布期间发现的问题及处理结果。

发布确认稳定后，可以删除开发机和服务器 `/tmp` 中的归档文件，但至少保留当前版本、上一个版本对应的镜像、发布目录和可验证数据备份。
