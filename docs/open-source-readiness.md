# 开源准备记录

[返回 README](../README.md) · [Pages 发布](github-pages.md)

2026-10-10 完成本地准备与验收，2026-10-14 补充原图来源比对、实际 Gitleaks 扫描、远端历史复查与 GitHub 设置。2026-10-16 仓库已公开，匿名访问验证通过；Pages 展示站尚未启用。本记录描述各检查点的实际验证范围。

2026-10-15 的迁移目标为独立私有仓库 `WowCoder/VideoX`，仅迁入清理后的主分支历史；旧私有仓库继续保持 Private。下述 2026-10-14 GitHub 平台结果均属于原仓库，不能替代新仓库的独立复核。本轮公开结果见下文；迁移边界见 [迁移计划](superpowers/plans/2026-10-15-videox-migration.md)。

## 源码与文档

- 使用 MIT；加入贡献、安全报告、Issue/PR 模板、Dependabot 和安全检查工作流。
- 移除含个人登录身份的本地迁移脚本，通用化短信身份与生产示例域名；环境文件、备份与常见密钥文件加入忽略规则。
- 2026-10-14 按原官网展示需求恢复三张原始图片，文件与私密备份中的原图逐字节一致；页面标为概念图或摄影参考，图片来源与署名核查记录见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
- README 分为项目能力、真实工作区截图、启动路径和可检查的工程亮点；详细说明拆到技术文档。
- 独立 Pages 入口复用原官网的布局、样式和图片，在开源展示模式中显示源码与文档入口，不显示登录或会员价格，也不加载应用路由、鉴权或 API。

## 实际验证

下表保留 2026-10-10 至 15 的历史验收；2026-10-16 的新鲜复核另列于后。

| 检查 | 环境与结果 |
| --- | --- |
| 后端单元测试 | 新建 Python 3.12 依赖环境，274 项通过；Python 3.11 也通过 |
| 前端单元测试 | Node 22，27 项通过 |
| 静态检查 | 前端 lint、后端 compileall、Alembic 单一迁移头通过 |
| 构建 | 用户应用、管理端、Pages 构建通过；Pages 项目路径和根路径均验证 |
| 配置 | 开发和生产示例 Compose 校验通过；未读取真实生产配置 |
| 依赖审计 | 2026-10-14 npm audit 零告警；pip-audit 2.10.1 完整解析当时后端 requirements 的 97 个包，零漏洞、零跳过、无忽略项 |
| 密钥扫描 | Gitleaks 8.30.1 在 `c148060` 检查点扫描全部本地引用的 29 个提交和 374 个可发布文件，精确排除两项已核实的测试值后零命中；例外边界反向验证通过 |
| 原仓库远端历史 | 2026-10-14，独立私密 mirror 核查 `main` 的 `d9fdb6c` 及全部 46 个向已认证客户端提供的引用，共 60 个可达提交；Gitleaks 零命中，已移除的身份脚本零可达对象、零相关历史提交，提交邮箱均为 GitHub noreply，清理前的旧主分支提交不可达 |
| 原仓库 GitHub CI | 2026-10-14，`main` 的 `c148060`、后续文档提交 `d9fdb6c`、`9535ebe` 均实际通过 Check 和 Security 工作流 |
| VideoX 迁移核查 | 2026-10-15，`53d3ac9` 检查点保留主分支 32 个干净提交、375 个文件，独立远端 tree 与本地完全一致；新仓库 46 个引用、62 个可达提交的 Gitleaks 零命中，旧身份脚本和清理前的原始提交均不存在，提交邮箱均为 GitHub noreply |
| VideoX GitHub CI | 2026-10-15，`53d3ac9` 实际通过新仓库 Check 和 Security，Pages 发布工作流按私有仓库条件跳过；旧敏感文件链接在新仓库返回 404 |
| VideoX 品牌统一 | 2026-10-15，隔离且断网的 Python 3.12 环境通过 275 项后端测试；前端 27 项测试、lint、应用/管理端/Pages 构建和 Compose 配置检查通过。原有图片字节未变，当前可发布源码 Gitleaks 零命中；历史数据兼容标识保留，既有部署切换见[配置说明](configuration.md#既有部署切换) |
| 浏览器 | 复用官网的 Pages 页面在桌面 1280 px、手机 390 px 下无横向溢出；导航、FAQ、示意动画与图片加载通过；此前邮箱登录、工作区与编辑器显示通过 |
| 数据库 | 独立空数据库完成全部 37 次迁移；原有应用数据库未参与测试 |
| 媒体流程 | 全部 AI Provider 与搜索关闭，邮箱注册/登录 → 原创视频上传与处理 → 手动分镜 → 主成片编排 → FFmpeg 导出 → 鉴权下载通过 |

媒体输入为 FFmpeg 生成的 3 秒测试图案和正弦音。输出为约 370 KB 的 MP4，FFprobe 确认 H.264/AAC、854×480、3.008 秒。测试使用独立 Docker 网络、数据卷和端口，不调用付费服务，不上传用户素材。[工作区截图](assets/workspace-smoke.jpg)来自这次运行。

依赖升级修复了当次审计发现的漏洞，包括 Tailwind 4 和与补丁版 Starlette 兼容的 FastAPI。浏览器要求见 [当前边界](limitations.md)。审计结果仅针对运行当日的已知数据库，不承诺没有未知漏洞。

Docker Hub 当时无法连接；容器验收复用了本机缓存的 Node 22 / Python 3.12 基础环境，分别运行全新 `npm ci` 和空 Python venv 的完整依赖安装。未验证当时从公网首次拉取基础镜像的网络链路。

密钥检查覆盖当前可发布文件和全部可达 Git 内容；此前还对本地配置中的真实凭证做了精确匹配，未发现命中。2026-10-14 使用校验官方 SHA-256 的 Gitleaks 8.30.1 完成实际扫描。未配置例外时仅命中测试中的幂等标识和 RFC 6238 公开 TOTP 测试向量；[配置](../.gitleaks.toml)保留全部默认规则，仅在 `generic-api-key` 规则下以精确路径与精确值的 AND 条件排除这两项。临时对照验证确认相同值放在其他路径、其他值放在这两个测试文件中仍能被检测。扫描报告只保存在仓库外的私密临时目录，凭证和个人信息不进入公开报告。

Security 工作流固定同一 Gitleaks 版本和配置，增量检查后扫描全部检出引用；上述检查点的云端结果已通过。远端缓存和旧构建产物需单独核对，CI 通过不代表旧历史已被服务器清除。本机旧 `backend/.venv` 含重复和过时依赖，存在已知漏洞；它不是上述完整审计使用的当前 requirements 环境，也不作为发布来源。更新本地运行环境时应按快速开始创建干净环境，避免沿用旧虚拟环境。

云端模型真实推理、支付交易、生产负载与灾难恢复不属于这次离线验收范围。

## 2026-10-16 公开前复核

- **远端基线 `ee0fa4b`**：独立核查 55 个远端引用、71 个可达提交（主分支 35 个）、1063 个可达 blob。历史、全部可达 blob、当前主分支快照与提交元数据四类 Gitleaks 扫描均零命中；作者与提交者邮箱均为 GitHub noreply，旧私密脚本及未清理提交均不可达。
- **本地工程检查**：前端 27 项测试、lint、应用/管理端/Pages 三个构建全部通过，包含开发依赖的完整 npm audit 零漏洞；后端 275 项测试、compileall、Alembic 单一迁移头 `037` 及开发/生产示例 Compose 校验通过。全新 Python 3.12 后端环境完整审计 99 个包（含临时工具 pip 26.2.1），零漏洞。
- **可选服务修复**：四个 local-ai 原 requirements 的完整审计发现真实已知漏洞；本轮修复分支更新四份清单及三个 Dockerfile 的 CPU 包约束，补上 Python 3.11 四服务安全审计矩阵和五个 Python 目录的每周 Dependabot 更新。修复后四份清单在 macOS ARM / Python 3.11 下均以默认 PyPI 完整解析并审计为零漏洞；最终采用的 `transformers==5.10.4` 未被撤回（非 yanked）。
- **CPU 兼容检查**：Linux aarch64 / Python 3.11 干净合并 venv 中，`torch==2.13.0+cpu`、`torchaudio==2.11.0+cpu` 与修复后的相关包真实导入成功，四服务模型入口导入通过；16 kHz → 8 kHz 重采样、Mel 计算、`pip check` 均通过，CUDA 为 `None`。
- **Linux 依赖复审**：Linux aarch64 / Python 3.11 的默认 PyPI 完整依赖图审计通过，ASR 99、OCR 31、embedding 75、reranker 100 个包均零漏洞、零跳过，包含三个 Torch 服务额外的 CUDA/NVIDIA/triton 依赖。
- **修复后远端与云端检查**：`d3eb7cc` 的远端固定快照包含主分支 36 个提交、58 个引用及 75 个可达提交，历史与新增元数据 Gitleaks 零命中。该提交的 GitHub [Check](https://github.com/WowCoder/VideoX/actions/runs/38884130867) 和 [Security](https://github.com/WowCoder/VideoX/actions/runs/38884131067) 均已实际成功，包含新增的四服务审计矩阵。机器人引用会继续更新，扫描结论对应已记录快照。
- **公开结果**：维护者确认平台检查通过并将仓库设为 Public；随后无认证 GitHub API 返回 `visibility=public`、`private=false`，README 可读取，禁用凭据助手的 HTTPS Git 读取成功，主分支为 `d3eb7cc`。平台告警由维护者在公开前核对。

规范 PyPI requirements 依赖图的审计不等于 CPU 镜像所有层或系统库的检查；上述 CPU 验证使用单一合并环境，未下载模型或进行真实推理，不是四个镜像各自的全量验收。

## 仓库迁移与发布流程

2026-10-14 完成三张原图的直接来源比对：NASA 概念图像素一致，月球照片与 NASA ISS038e037342 逐字节一致，银河图与作者 Commons 原图在缩放、转码后匹配。原图全部保留，修正先前错误的 ESA 月球署名；保留 NASA 使用说明和银河图的 CC BY-SA 4.0 署名、来源及变换说明，见 [第三方说明](../THIRD_PARTY_NOTICES.md)。

旧私有仓库的目标分支已经清理、推送并通过当时的 CI；已删除 6 次旧 Check 记录，原有的 12 个依赖或工具缓存均为清理后创建。原仓库的 Description、8 个 Topics、Dependency graph、Dependabot alerts 和 Dependabot security updates 已设置。原提交的服务器缓存仍需通过已提交的 GitHub Support 工单处理；这些平台记录只适用于原仓库，详情见 [历史处理说明](history-cleanup.md)。不要向原仓库重新推送未清理历史。

`WowCoder/VideoX` 使用独立的新仓库，仅迁入清理后的主分支及其祖先，不采用 Fork 或仓库转移。原仓库的服务器缓存、Actions 日志、附件和未审计引用不属于此次迁移内容。原仓库继续保持 Private，其缓存清除工单不作为独立新仓库公开的前置条件。

新仓库已为 **Public**，Website 仍留空，Pages 尚未发布。源码、克隆、Issue、安全反馈链接和 Pages 默认项目路径使用 VideoX。迁移检查点保留了当时的应用标识；后续品牌统一为 VideoX，原有图片保留。Pages 工作流需要仓库为 Public、`PAGES_ENABLED=true` 且分支为 `main` 才会发布，普通 Check 中的静态站构建不发布站点。

2026-10-15 已独立确认新仓库的 Description、8 个 Topics 及 Dependency graph、Dependabot alerts、Dependabot security updates 设置；当时有 15 个由新仓库配置自动创建的 Dependabot 依赖 PR，没有从原仓库迁入或自动合并。这是历史记录，不代表本轮 PR 或告警数量。本地默认 `origin` 指向 VideoX，旧私有仓库远端继续保留。

后续维护或再次迁移时，沿用以下流程：

1. 迁移时先使用独立的 Private 仓库，核对远端主分支与已审核的迁移提交完全一致；检查全部提供的分支、标签、PR 引用及提交元数据，确认没有清理前身份脚本或私人邮箱。
2. 在新仓库运行 Check 和 Security，以新仓库实际结果为准；独立检查其 Description、Topics 和依赖保护设置。不得用原仓库的设置或 CI 结果代替。
3. 本轮待验证项、云端 CI 和平台告警核实无阻塞后，将新仓库设为 Public；按届时可用功能配置私密漏洞报告、Secret scanning / Push protection 与主分支保护。
4. 按 [Pages 指南](github-pages.md)显式设置发布变量、启用 Pages，核对实际站点后再填写 Website URL。当前预计项目路径为 `/VideoX/`，不声称站点已上线。
5. 只从已检查的干净源码构建公开镜像或发布包，不上传环境文件、原始备份、私人媒体或旧部署产物。首个版本的演示与验证说明应使用自有素材，并标明实际验证范围。

建议 Topics：`video-editing`、`ai-workflows`、`human-in-the-loop`、`fastapi`、`react`、`celery`、`pgvector`、`ffmpeg`。不要把尚未实现的通用自主 Agent 或多人协作当成项目标签或已完成能力。
