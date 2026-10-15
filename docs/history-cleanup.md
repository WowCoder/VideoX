# Git 历史处理与仓库迁移

[返回开源准备记录](open-source-readiness.md)

本说明记录原 `WowCoder/OpenVMA` 仓库的历史清理。2026-10-15，维护者选择创建独立的私有仓库 `WowCoder/VideoX`，仅迁入清理后的主分支及其祖先，公开须再次得到维护者确认。新仓库不采用 Fork 或仓库转移，不导入原服务器上的旧缓存、Actions 运行记录、附件或未审计引用。原仓库继续保持 Private；原仓库的 Support 缓存清除工单不作为独立新仓库公开的前置条件。

## 原仓库的清理记录

原仓库最初采用“保留原仓库，清理受影响历史”的方式。历史删除包括含个人身份的本地迁移脚本；历史中的特定私人身份、短信身份与生产示例域名使用通用值替换，个人提交邮箱替换为 GitHub noreply 地址，保留作者显示名及提交归属。旧展示图曾因来源未核实从历史中移除，2026-10-14 按原官网需求仅恢复了三张原图文件；该恢复没有带回私人身份脚本或原始 Git 引用。

处理流程为：仓库外保存权限受限的恢复 bundle → 在独立 mirror 中试运行过滤 → 检查全部可达对象与提交元数据 → 对本地仓库应用同一过滤 → 核对工作区内容和引用。恢复 bundle 含原始私人信息，必须保持私密，不能上传到仓库、公开附件或共享网盘。

本地历史清理不等于远端更新。过滤会改变受影响提交及其后续提交的 SHA，其他克隆必须协调重新克隆或重置，避免把旧历史合并回来。已验证实现保存在 `codex/open-source-preparation` 分支，并于 2026-10-14 经审查后更新到远端 `main`；独立 SSH 查询确认发布检查点一致。该检查点的 GitHub Check、Security 已实际通过。

后续文档提交以正常快进更新远端 `main` 至 `d9fdb6c`。2026-10-14 的独立私密 mirror 审计覆盖该主分支、15 个新建 Dependabot 分支及对应的 15 个 PR head、15 个 PR merge，共 46 个引用、60 个可达提交，审计前后向已认证客户端提供的引用一致。Gitleaks 8.30.1 零命中；已移除身份脚本的可达对象和相关历史提交均为零；所有作者邮箱为 GitHub users noreply，提交者邮箱为 GitHub users noreply 或 GitHub 平台 noreply，未出现私人邮箱；清理前的旧主分支提交不可达。该审计没有显式获取旧对象，也不覆盖服务器内部引用和不可达对象缓存。

远端更新前记录各目标分支的原始 SHA，以明确的 `--force-with-lease=<ref>:<old-sha>` 保护更新；不要直接使用无条件 `--force` 或 `git push --mirror`，后者可能误删不相关引用。分支保护可能需要仓库管理员临时授权具体更新。

除分支和标签外，还需核查 GitHub 的 PR 引用、缓存、附件、Actions 日志/产物及旧容器镜像。旧克隆和第三方副本不能靠一次 force push 自动删除。若发现真实密钥外泄，应先撤销或轮换对应密钥；这次精确匹配未发现本地配置的真实凭证进入 Git。

2026-10-14 的登录后核查证实旧提交缓存仍可访问已移除的私人身份信息，仓库因此暂时保持私有，Website 留空。仓库描述、8 个 Topics 已保存，Dependency graph、Dependabot alerts、Dependabot security updates 已确认开启。经管理员确认，6 次旧 Check 运行记录已永久删除；重新加载服务器列表后核实目标 ID 全部消失，干净主分支 Check、Security 和新 Dependabot 运行保留。GitHub Support 的缓存清除工单已创建，完整说明已保存到同一私密工单，当前状态为 Open；没有发送实际私人值或原始备份。原仓库若再次公开，应得到缓存清除确认、再次核查旧文件页面不可访问。不要把原始 SHA 的源码链接或私人值贴到公开讨论中。

GitHub 的[敏感数据删除说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)解释历史重写、协作者处理和缓存清理范围。正式公开前以远端检查结果为准。
