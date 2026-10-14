# GitHub Pages 展示站

[返回 README](../README.md)

展示站通过独立静态 React/Vite 入口复用应用现有的 [SiteHome](../frontend/src/views/SiteHome.tsx) 首页及其样式，使用 `open-source` 模式介绍项目流程与源码，链接到仓库和部署文档。它不加载 `App`、登录状态或应用 API，也不提供付费会员交互。展示内容与概念图不是已生成视频或完整工作台的可操作演示。

## 本地构建与预览

需要 Node 22。在项目根目录执行：

```bash
cd frontend
npm ci
npm run build:pages
npm run preview:pages
```

构建输出 `frontend/dist-pages/`，默认 base 为 `/OpenVMA/`。预览服务默认在 `http://127.0.0.1:4175/OpenVMA/`；检查真实终端输出后打开对应地址。

入口为 [pages/index.html](../frontend/pages/index.html)、[pagesMain.tsx](../frontend/src/pagesMain.tsx) 和 [vite.pages.config.ts](../frontend/vite.pages.config.ts)。[base.css](../frontend/pages/base.css) 仅提供首页所需的基础重置，不加载应用的全局工作区样式。独立的 `frontend/pages/public/` 携带品牌 SVG 和官网原有的三张概念图、摄影参考；修改原图时同步该目录的对应副本。资源路径使用 Vite `BASE_URL`，支持 GitHub Pages 的项目子路径。图片来源记录见 [第三方说明](../THIRD_PARTY_NOTICES.md)，未核实的记录应在正式公开前补齐。不要将用户照片、项目媒体、环境文件或 API Key 放入公开静态资源。

若仓库更名或改用自定义域名，在构建时设置完整首尾斜线 base：

```bash
PAGES_BASE_PATH=/ npm run build:pages
```

改用其他项目路径时同步工作流、文档链接与预览 URL。无需为此配置应用后端。

## 仓库中启用发布

仓库提供 [Pages 工作流](../.github/workflows/pages.yml)，支持手动运行和主分支触发。发布前先把已检查的实现合入对应主分支；本地构建不会自动开启 Pages 或发布远端内容。

1. 在 GitHub 仓库 Settings → Actions 中允许工作流运行。
2. 打开 Settings → Pages，把 Build and deployment 的 Source 设为 **GitHub Actions**。
3. 在 Actions 中打开 Pages 工作流，选择 `main` 手动执行；当前工作流仅允许 `main` 构建和部署，其他分支的手动运行会跳过这些任务。也可通过 `main` 上相关路径的提交触发。
4. 检查 build/deploy 任务与 `github-pages` environment 的结果，以 GitHub 返回的实际页面 URL 为准。
5. 打开发布地址，检查项目路径下 CSS、图片、移动布局、源码链接和文档链接。
6. 在仓库首页 About 旁点击编辑，把 Website 设置为实际发布 URL。

对于 `WowCoder/OpenVMA`，默认预期 URL 是 `https://WowCoder.github.io/OpenVMA/`。这只是命名推导，文档不声称它已上线。Fork 的用户名不同，实际地址也不同；组织策略或 environment 保护规则可能需要仓库管理员处理。

## 检查与限制

展示站访问不应产生应用 `/api` 或 WebSocket 请求。公开站点只展示项目说明，不提供账号注册、视频上传、生成任务或编辑器后端。完整应用需要按 [快速开始](getting-started.md) 本地运行或按 [生产手册](../deploy/README.md) 部署。

修改展示文案时以当前源码和验证记录为准，不添加未经测量的质量、性能或成功率数字。新增展示资产先确认再分发权限，并更新 [第三方说明](../THIRD_PARTY_NOTICES.md)。
