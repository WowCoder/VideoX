# Contributing to VideoX

感谢你帮助改进 VideoX。开始前请阅读 [快速开始](docs/getting-started.md)和[架构说明](docs/architecture.md)。

## 问题反馈

通过 [GitHub Issues](https://github.com/WowCoder/VideoX/issues)报告可复现的问题或提出功能建议。说明版本、运行方式、操作步骤、预期与实际结果，并提供脱敏后的错误日志。不要附上环境文件、访问令牌、手机号、私有素材或带签名的媒体 URL。

安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 提交改动

1. 从最新 `main` 创建功能分支；较大功能先通过 Issue 讨论需求和边界。
2. 保持改动聚焦。业务结果来自真实数据和任务；开发预览与测试数据需要明确区分。
3. 为行为变化添加能复现问题的测试。文案和配置通过实际使用路径验证。
4. 在 PR 中说明问题、最终行为、验证命令与尚未覆盖的场景。

## 验证

容器运行后，在仓库根目录执行：

```bash
make check
```

非 Docker 开发的检查入口见 [开发指南](docs/development.md)。宣传站改动还需运行 `cd frontend && npm run build:pages`，在 `/VideoX/` 路径预览，检查移动端、键盘导航、图片与链接。

真实供应商调用可能产生费用，不是 PR 检查的必要步骤。注明测试使用的 Provider；未经配置和授权不要执行付费冒烟测试。

## 代码与素材

提交前检查 `git diff --cached`，只加入本次需要的文件。保持 `.env*`、私钥、数据库备份与用户数据在仓库外。新增第三方代码、模型、图片或示例媒体时，在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)记录出处及适用许可。

项目代码采用 [MIT](LICENSE)。提交贡献时，应确保你有权以该协议提供这些改动；第三方依赖和模型仍遵循其自身协议。
