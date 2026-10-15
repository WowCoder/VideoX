SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
BACKEND := $(COMPOSE) exec -T backend
FRONTEND := $(COMPOSE) exec -T frontend

export VIDEOX_TEST_ACCOUNT_EMAIL := $(EMAIL)
export VIDEOX_TEST_ACCOUNT_PASSWORD := $(PASSWORD)
export VIDEOX_TEST_ACCOUNT_NAME := $(if $(strip $(NAME)),$(NAME),测试账号)

.PHONY: help setup doctor \
	up up-ai rebuild rebuild-ai stop down restart restart-backend restart-worker ps \
	logs logs-backend logs-worker logs-frontend logs-ai \
	test backend-test backend-compile frontend-install frontend-test lint frontend-build compose-check check \
	db-upgrade db-current db-heads db-history db-revision db-check \
	shell-backend shell-frontend shell-db worker-ping worker-tasks health config \
	reindex reindex-all create-test-account reset-ai-usage backfill-video-previews

backfill-video-previews: ## 为缺少代理的历史视频生成浏览器预览（可传 LIMIT=20 或 ASSET_ID=...）
	@if [[ -n "$(LIMIT)" ]] && ! [[ "$(LIMIT)" =~ ^[1-9][0-9]*$$ ]]; then \
		echo "LIMIT 必须是正整数" >&2; \
		exit 1; \
	fi
	@$(BACKEND) python scripts/backfill_video_previews.py \
		$(if $(strip $(LIMIT)),--limit $(LIMIT),) \
		$(if $(strip $(ASSET_ID)),--asset-id $(ASSET_ID),)

help: ## 显示可用命令
	@awk 'BEGIN {FS = ":.*## "; printf "VideoX 常用命令\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-24s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## 首次初始化 .env（已存在时不会覆盖）
	@if [[ -f .env ]]; then \
		echo ".env 已存在，保持不变"; \
	else \
		cp .env.example .env; \
		echo "已从 .env.example 创建 .env，请按需填写配置"; \
	fi

doctor: ## 检查 Docker、Compose、Node、npm 与 Python 环境
	@command -v docker >/dev/null || { echo "未找到 docker" >&2; exit 1; }
	@$(COMPOSE) version
	@command -v node >/dev/null && node --version || echo "提示：宿主机未安装 Node（Docker 工作流不受影响）"
	@command -v npm >/dev/null && npm --version || echo "提示：宿主机未安装 npm（Docker 工作流不受影响）"
	@command -v python3 >/dev/null && python3 --version || echo "提示：宿主机未安装 python3（Docker 工作流不受影响）"
	@$(COMPOSE) config --quiet
	@echo "环境检查通过"

up: setup ## 启动基础应用
	@$(COMPOSE) up -d

up-ai: setup ## 启动基础应用和本地 AI 服务
	@$(COMPOSE) --profile local-ai up -d

rebuild: setup ## 重新构建并启动基础应用
	@$(COMPOSE) up -d --build

rebuild-ai: setup ## 重新构建并启动基础应用和本地 AI 服务
	@$(COMPOSE) --profile local-ai up -d --build

stop: ## 停止服务但保留容器
	@$(COMPOSE) stop

down: ## 停止并移除容器和网络（保留数据卷）
	@$(COMPOSE) down

restart: ## 重启应用进程，不重启数据库、缓存、存储和本地 AI
	@$(COMPOSE) restart backend frontend celery-worker celery-beat

restart-backend: ## 重启后端 API
	@$(COMPOSE) restart backend

restart-worker: ## 重启 Celery Worker，使任务代码改动生效
	@$(COMPOSE) restart celery-worker

ps: ## 查看服务状态
	@$(COMPOSE) ps

logs: ## 持续查看应用日志
	@$(COMPOSE) logs -f backend frontend celery-worker celery-beat

logs-backend: ## 持续查看后端日志
	@$(COMPOSE) logs -f backend

logs-worker: ## 持续查看 Celery Worker 日志
	@$(COMPOSE) logs -f celery-worker

logs-frontend: ## 持续查看前端日志
	@$(COMPOSE) logs -f frontend

logs-ai: ## 持续查看本地 AI 服务日志
	@$(COMPOSE) logs -f local-embedding local-reranker local-asr local-ocr

test: backend-test ## 运行后端单元测试

backend-test: ## 运行后端单元测试
	@$(BACKEND) python -m unittest discover -s tests -v

backend-compile: ## 编译检查后端 Python 文件
	@$(BACKEND) python -m compileall -q app alembic scripts tests

frontend-install: ## 按 lockfile 安装/修复前端容器依赖
	@$(FRONTEND) npm install

frontend-test: ## 运行前端 Node 单元测试
	@$(FRONTEND) npm test

lint: ## 运行前端 ESLint
	@$(FRONTEND) npm run lint

frontend-build: ## 运行前端类型检查和生产构建
	@$(FRONTEND) npm run build

compose-check: ## 校验 Docker Compose 配置
	@$(COMPOSE) config --quiet

check: compose-check backend-test backend-compile frontend-test lint frontend-build ## 运行提交前完整检查
	@echo "全部检查通过"

db-upgrade: ## 升级数据库到最新迁移
	@$(BACKEND) python -m alembic upgrade head

db-current: ## 查看数据库当前迁移版本
	@$(BACKEND) python -m alembic current

db-heads: ## 查看代码中的迁移头
	@$(BACKEND) python -m alembic heads

db-history: ## 查看迁移历史
	@$(BACKEND) python -m alembic history

db-revision: ## 生成迁移：make db-revision MSG="说明"
	@test -n "$(strip $(MSG))" || { echo '缺少 MSG，例如：make db-revision MSG="add field"' >&2; exit 1; }
	@$(BACKEND) python -m alembic revision --autogenerate -m "$(MSG)"

db-check: ## 检查 ORM 与迁移差异（历史基线可能产生已知提示）
	@$(BACKEND) python -m alembic check

shell-backend: ## 进入后端容器 Shell
	@$(COMPOSE) exec backend bash

shell-frontend: ## 进入前端容器 Shell
	@$(COMPOSE) exec frontend sh

shell-db: ## 进入 PostgreSQL 控制台
	@$(COMPOSE) exec db psql -U videox -d videox

worker-ping: ## 检查 Celery Worker 是否响应
	@$(BACKEND) celery -A app.tasks.celery_app inspect ping

worker-tasks: ## 查看 Celery 活跃、等待和定时任务
	@$(BACKEND) celery -A app.tasks.celery_app inspect active
	@$(BACKEND) celery -A app.tasks.celery_app inspect reserved
	@$(BACKEND) celery -A app.tasks.celery_app inspect scheduled

health: ## 请求后端健康检查
	@curl --fail --show-error http://localhost:8000/api/health
	@echo

config: ## 输出合并后的 Docker Compose 配置
	@$(COMPOSE) config

reindex: ## 重建部分向量：make reindex LIMIT=20
	@if [[ -n "$(LIMIT)" ]] && ! [[ "$(LIMIT)" =~ ^[1-9][0-9]*$$ ]]; then \
		echo "LIMIT 必须是正整数" >&2; \
		exit 1; \
	fi
	@$(BACKEND) python scripts/reindex_embeddings.py $(if $(strip $(LIMIT)),--limit $(LIMIT),)

reindex-all: ## 强制重建全部向量，需 CONFIRM=1
	@test "$(CONFIRM)" = "1" || { echo "该操作会重算全部历史向量，请增加 CONFIRM=1" >&2; exit 1; }
	@$(BACKEND) python scripts/reindex_embeddings.py --all

create-test-account: ## 创建测试账号：EMAIL=... PASSWORD=... [NAME=...] [RESET_PASSWORD=1]
	@test -n "$(strip $(EMAIL))" || { echo "缺少 EMAIL" >&2; exit 1; }
	@test -n "$(PASSWORD)" || { echo "缺少 PASSWORD" >&2; exit 1; }
	@$(BACKEND) python -c 'import os, sys; value = os.getenv("ENVIRONMENT", ""); sys.exit("容器未注入 ENVIRONMENT，请先执行 make up 以更新后端容器") if not value else None; sys.exit("生产环境禁止管理测试账号") if value.lower() == "production" else None'
	@$(COMPOSE) exec -T \
		-e VIDEOX_TEST_ACCOUNT_EMAIL \
		-e VIDEOX_TEST_ACCOUNT_PASSWORD \
		-e VIDEOX_TEST_ACCOUNT_NAME \
		backend python scripts/manage_test_account.py create \
		$(if $(filter 1,$(RESET_PASSWORD)),--reset-password,)

reset-ai-usage: ## 重置账号 AI 生图/视频用量：EMAIL=... CONFIRM=1
	@test -n "$(strip $(EMAIL))" || { echo "缺少 EMAIL" >&2; exit 1; }
	@test "$(CONFIRM)" = "1" || { echo "该操作会修改账号用量，请增加 CONFIRM=1" >&2; exit 1; }
	@$(BACKEND) python -c 'import os, sys; value = os.getenv("ENVIRONMENT", ""); sys.exit("容器未注入 ENVIRONMENT，请先执行 make up 以更新后端容器") if not value else None; sys.exit("生产环境禁止重置 AI 用量") if value.lower() == "production" else None'
	@$(COMPOSE) exec -T \
		-e VIDEOX_TEST_ACCOUNT_EMAIL \
		backend python scripts/manage_test_account.py reset-ai-usage
