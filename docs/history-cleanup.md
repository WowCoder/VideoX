# Git 历史处理说明

[返回开源准备记录](open-source-readiness.md)

本项目采用“保留原仓库，清理受影响历史”的方式。历史删除包括含个人身份的本地迁移脚本和来源不完整的旧展示照片；历史中的特定私人身份、短信身份与生产示例域名使用通用值替换，个人提交邮箱替换为 GitHub noreply 地址，保留作者显示名及提交归属。

处理流程为：仓库外保存权限受限的恢复 bundle → 在独立 mirror 中试运行过滤 → 检查全部可达对象与提交元数据 → 对本地仓库应用同一过滤 → 核对工作区内容和引用。恢复 bundle 含原始私人信息，必须保持私密，不能上传到仓库、公开附件或共享网盘。

本地历史清理不等于远端更新。过滤会改变受影响提交及其后续提交的 SHA，其他克隆必须协调重新克隆或重置，避免把旧历史合并回来。已验证实现保存在 `codex/open-source-preparation` 分支；在更新远端 `main` 前应先审查并将其整合为发布版本。

远端更新前记录各目标分支的原始 SHA，以明确的 `--force-with-lease=<ref>:<old-sha>` 保护更新；不要直接使用无条件 `--force` 或 `git push --mirror`，后者可能误删不相关引用。分支保护可能需要仓库管理员临时授权具体更新。

除分支和标签外，还需核查 GitHub 的 PR 引用、缓存、附件、Actions 日志/产物及旧容器镜像。旧克隆和第三方副本不能靠一次 force push 自动删除。若发现真实密钥外泄，应先撤销或轮换对应密钥；这次精确匹配未发现本地配置的真实凭证进入 Git。

GitHub 的[敏感数据删除说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)解释历史重写、协作者处理和缓存清理范围。正式公开前以远端检查结果为准。
