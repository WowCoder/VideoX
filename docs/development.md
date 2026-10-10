# 开发指南

[返回 README](../README.md) · [快速开始](getting-started.md) · [贡献](../CONTRIBUTING.md)

## 代码入口

| 路径 | 用途 |
| --- | --- |
| `backend/app/api/` | FastAPI 业务接口 |
| `backend/app/models/`、`schemas/` | 数据模型与接口约束 |
| `backend/app/services/` | 工作区、Provider、队列、渲染计划等 |
| `backend/app/tasks/` | Celery 异步工作 |
| `backend/alembic/`、`tests/` | 迁移与后端测试 |
| `frontend/src/` | React 工作台、管理端和独立 Pages 入口 |
| `local-ai/` | 可选 Embedding、Reranker、ASR、OCR 服务 |
| `deploy/`、`compose.prod.yml` | 生产网关、发布、备份和恢复 |

宿主机开发使用 Node 22、Python 3.12 和 FFmpeg/FFprobe。Node 前端测试使用 `--experimental-strip-types`；不要以旧 README 的 Node 20 最低要求作为完整检查环境。

## 日常检查

运行开发 Compose 后，在根目录执行：

```bash
make help
make check
```

`make check` 校验 Compose，运行后端 unittest/compileall、前端 Node 测试、ESLint 和应用 production build。管理端与 Pages 单独构建：

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
npm run build:admin
npm run build:pages
```

三个产物分别位于 `frontend/dist/`、`frontend/dist-admin/`、`frontend/dist-pages/`。Pages 配置与应用 Vite 配置独立，见 [Pages 指南](github-pages.md)。

宿主机后端虚拟环境中执行：

```bash
cd backend
python -m unittest discover -s tests -v
python -m compileall -q app alembic scripts tests
```

这些是本地验证命令，不表示每种硬件、外部模型或生产部署都已经通过验证。模型与真实媒体验收需要按场景单独记录。

## Worker 与数据库

宿主机完整队列启动见 [快速开始](getting-started.md)。修改异步任务后重启 Worker；开发容器中可以使用 `make restart-worker`。更改 `.env` 时使用 `docker compose up -d`，不是仅重启已有容器。

迁移前了解当前版本与目标：

```bash
make db-current
make db-heads
make db-history
make db-upgrade
```

新增迁移可用 `make db-revision MSG="change description"`；人工检查生成内容及已有数据兼容性。生产迁移、停止写入备份与 schema 回滚边界见 [发布手册](../deploy/release.md)。

切换 Embedding Provider/模型后，用真实模型重建向量。先确认当前服务 healthy，再测试少量素材：

```bash
docker compose exec -T backend python scripts/reindex_embeddings.py --limit 20
```

需要强制重建时：

```bash
docker compose exec -T backend python scripts/reindex_embeddings.py --all
```

脚本失败时记录真实失败，不写随机或零向量。不同 Embedding 空间不能混用，即使都是 1024 维。

## 管理与维护

用户账号可直接邮箱注册。测试账号维护脚本仅供开发/测试，已有账号不会默认改密码；生产环境拒绝该维护路径。完整选项可查看 `make help` 与 [脚本](../backend/scripts/manage_test_account.py)。

运营后台需单独运行 `npm run dev:admin`，并通过 [管理员脚本](../backend/scripts/manage_admin.py) 创建独立账号与 TOTP。管理员会话、登录锁定与密钥配置见 [配置](configuration.md) 和 [生产部署](../deploy/README.md)。

后端/Worker/Beat Docker 进程使用非 root 用户。生产网关隐藏普通用户侧管理路径；不要将开发 Vite 服务直接暴露作为生产管理入口。

## 改动时保留的约束

异步操作要保留项目/镜头版本检查，媒体任务只有真实结果持久化后才能标为成功。不要在普通保存、匹配或页面刷新中隐式启动付费生成。新增 Provider 要验证请求/结果边界、失败语义与费用重试窗口；导出修改要使用真实短媒体验证计划和 FFmpeg 输出。

提交问题时提供步骤、环境、命令结果和经过脱敏的日志。不要提交 `.env`、媒体账号数据、真实密钥或未知授权素材；贡献与安全处理见根目录说明。
