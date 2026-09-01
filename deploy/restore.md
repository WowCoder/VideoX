# OpenVMA 恢复演练与灾难恢复

恢复会覆盖真实数据，因此仓库不提供自动执行的 destructive restore 脚本。以下步骤必须由运维人员确认备份、目标环境和停机窗口后人工执行，优先在隔离环境演练。

## 1. 校验备份

选择一个完整备份目录，检查 `manifest.txt`。如果存在 `SHA256SUMS`：

```bash
cd /srv/openvma/backups/<timestamp>
sha256sum --check SHA256SUMS
```

确认 `postgres.dump` 非空，`minio/` 中包含预期对象，manifest 中的 Git revision 和镜像标签可以取得。

## 2. 停止写入

先在雷池启用维护页或临时阻断业务流量，然后停止会产生写入的进程：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  stop gateway admin-gateway backend celery-worker celery-beat
```

不要在 Worker 仍处理媒体或导出任务时恢复数据库/对象存储。

## 3. PostgreSQL 恢复策略

最安全的方法是在新的 PostgreSQL 实例或新数据库名中恢复，并验证 Alembic 版本、表数量、关键账号、项目和任务数据，再切换应用连接。示例：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  exec -T db createdb -U openvma openvma_restore

docker compose -f compose.prod.yml --env-file .env.production \
  exec -T db pg_restore -U openvma -d openvma_restore --no-owner --no-privileges \
  < backups/<timestamp>/postgres.dump
```

实际用户名和数据库名必须以 `.env.production` 为准。验证通过前不要删除原数据库。若必须覆盖原数据库，需要先终止连接、删除并重建数据库，这属于不可逆操作，应由数据库管理员单独复核命令和备份后执行。

## 4. MinIO 恢复策略

优先恢复到新的 bucket，例如 `openvma-media-restore`，验证对象数量、抽样哈希、视频 Range 播放和预签名 URL，再切换配置。可以使用生产 Compose 中的 MinIO 镜像启动一次性 `mc`：

```bash
docker compose -f compose.prod.yml --env-file .env.production run --rm --no-deps \
  --entrypoint /bin/sh \
  -v /srv/openvma/backups/<timestamp>:/backup:ro \
  minio-init -c \
  'mc alias set restore http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" && mc mb --ignore-existing restore/openvma-media-restore && mc mirror --overwrite /backup/minio restore/openvma-media-restore'
```

不要在未确认的情况下对生产 bucket 使用 `mc mirror --remove`，它会删除备份中不存在的线上对象。

## 5. 恢复应用版本

使用 manifest 记录的 Git revision 和镜像 tag。数据库恢复完成后，确认该版本对应的 Alembic schema；不要盲目执行新代码的 `alembic upgrade head`。随后启动应用并仅做内部健康检查：

```bash
docker compose -f compose.prod.yml --env-file .env.production \
  up -d backend celery-worker celery-beat gateway admin-gateway

OPENVMA_ENV_FILE=/srv/openvma/.env.production ./deploy/healthcheck.sh
```

## 6. 业务验证与恢复流量

至少验证登录、项目列表、素材播放、任务列表、对象下载、WebSocket、一次小文件上传和一次不产生额外费用的安全业务流程。确认日志没有持续数据库、Redis 或 MinIO 错误后，再在雷池取消维护策略并恢复公网流量。

每次演练应记录恢复点目标（RPO）、实际恢复时间（RTO）、失败步骤和修订项。未经过恢复演练的备份只能视为“已生成文件”，不能视为已经具备灾难恢复能力。
