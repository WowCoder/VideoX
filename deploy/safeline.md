# 雷池 SafeLine 配置说明

雷池负责公网 80/443、TLS、WAF、CC/Bot 防护和域名转发；OpenVMA 内部 Nginx 负责 React SPA、API、WebSocket、1 GiB 上传与 MinIO Range 代理。不要把 PostgreSQL、Redis、Backend、MinIO Console 或本地 AI 直接添加为雷池上游。

## 前置条件

- 建议使用至少 9.3.2 版本：官方版本记录显示该版本修复了部分 WebSocket Upgrade 5xx；9.3.1 起支持路径转发和自定义 XFF 提取。
- DNS 中将应用域名、后台域名与媒体域名解析到雷池公网 IP。
- OpenVMA `gateway` 与 `admin-gateway` 已健康，且雷池容器或节点能分别访问 `GATEWAY_BIND_IP:GATEWAY_PORT` 和 `ADMIN_GATEWAY_BIND_IP:ADMIN_GATEWAY_PORT`。
- 主机防火墙只允许雷池到该内部端口的流量。

## 创建三个应用

在雷池中分别创建：

| 用途 | 域名示例 | 上游 |
| --- | --- | --- |
| React、REST API、WebSocket | `app.example.com` | `http://服务器可达内网IP:8080` |
| 独立运营后台 | `admin.example.com` | `http://服务器可达内网IP:8081` |
| MinIO 媒体与签名 URL | `media.example.com` | `http://服务器可达内网IP:8080` |

应用域名和媒体域名指向用户网关，后台域名单独指向后台网关。必须保留原始 Host 和查询字符串，否则 MinIO 预签名 URL 会验签失败。不要把媒体域名指向 MinIO Console 的 9001 端口。

当前 MVP 决策为暂时将 `admin.example.com` 开放到公网，不配置 VPN 或固定出口 IP 白名单。该模式下必须启用 HTTPS、WAF 和 CC/Bot 防护，并保持 `.env.production` 中的 `RATE_LIMIT_ENABLED=true`；后台登录还会受到按来源 IP 的认证接口限流和管理员账号失败锁定保护。不要依赖不公开的路径或域名名称，所有后台请求仍必须通过独立管理员登录与 TOTP MFA。公网开放属于过渡策略，具备条件后应升级为 VPN 或固定出口 IP 白名单。

为三个应用配置正式证书并启用 HTTPS。HTTP 应重定向到 HTTPS。HSTS 建议在雷池这一 TLS 终止层配置，确认所有子域名均支持 HTTPS 后再考虑 `includeSubDomains`。

## WebSocket

任务推送路径为：

```text
/api/ws/jobs
```

雷池官方 FAQ 说明默认支持 WebSocket 转发，但不检测 WebSocket 帧内攻击。上线验收时必须确认浏览器握手返回 `101 Switching Protocols`、客户端收到 `auth_ok`，并观察真实任务更新。即使 WebSocket 暂时断开，前端任务轮询仍保留为一致性兜底。

## 来源 IP 与限流

OpenVMA Backend 使用转发后的客户端地址执行应用级限流。雷池应覆盖或可信提取 `X-Forwarded-For`，内部 Nginx 会继续追加代理链。由于 Backend 只在 Docker 私有网络内开放，并且内部 8080 受防火墙限制，外部用户不能绕过雷池直接伪造转发头。

应用级限流与雷池 CC/Bot 策略需要同时保留：雷池负责边缘拦截，Backend 在 Redis 中做最后一道按客户端地址计数的保护。

## 1 GiB 上传验收

OpenVMA Backend 的权威上限是精确 `1 GiB = 1073741824` 字节；内部 Nginx 设置为 `1100m`，为 multipart 边界和请求头留余量。雷池公开文档没有对超大请求体代理给出可依赖的统一上限承诺，因此不能只根据配置推断成功，必须通过真实链路测试：

1. 上传一个普通有效媒体文件，确认雷池、Nginx、FastAPI、MinIO 全链路成功。
2. 上传一个接近但不超过 1 GiB 的有效媒体文件，确认不会在雷池处提前被拒绝或中断。
3. 上传一个超过 1 GiB 的文件，确认最终得到 Backend 的 413，而不是 502/504 或连接重置。
4. 观察雷池事件、内部 Nginx、Backend 和 MinIO 日志，确认请求没有被缓存到内存或临时磁盘耗尽。
5. 记录实测所需的雷池请求体和上游超时配置；升级雷池后重复回归。

如果雷池版本或策略无法稳定代理 1 GiB 请求，应优先评估 MinIO 直传/分片上传的后续架构，而不是降低 WAF 防护或将 Backend 暴露公网。

## 官方参考

- [添加应用](https://help.waf-ce.chaitin.cn/node/01973fc6-e14a-7234-8acd-bdba21c8b3f3)
- [常见问题与 WebSocket](https://help.waf-ce.chaitin.cn/node/01975855-cd7d-78fb-a354-d2aa65a53cce)
- [版本记录](https://help.waf-ce.chaitin.cn/node/0197787e-b70e-756e-b9d5-69d0a707144a)
- [静态文件托管](https://help.waf-ce.chaitin.cn/node/01973fc6-e103-7477-a7fb-ba7919d1676d)
