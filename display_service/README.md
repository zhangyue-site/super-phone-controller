# 106 端额度与交互展示

`python3 -m display_service.app` 仅监听 `127.0.0.1:18943`，由 Nginx 的独立 `/phone-controller/` 路径提供 TLS。

`/etc/phone-controller/devices.example.json` 保存设备 ID 到随机设备令牌的映射；不使用模型密钥或 tools 管理令牌。仅提供额度白名单摘要、1-bit 位图和 PNG，不转发原始 Cookie、账号身份或上游错误正文。

- `GET /status`：本设备交互与额度摘要。
- `GET /screen.bin?page=0|1`：200×200，逐行 MSB-first，白色位为1，共5000字节。
- `GET /screen.png?page=0|1`：同一渲染器的验收预览。
- `POST /stop`：记录本设备停止请求。响应明确 `actuatorConnected:false`，不宣称手机动作已停止。

所有接口要求 `Authorization: Bearer <设备令牌>`。当前没有手机控制执行器，不应发布虚假的 running/done 状态。

服务器发起状态更新：

```sh
cd /srv/phone-controller/server
python3 -m display_service.control epaper-01 --state waiting --task '等待手机接入'
```

状态文件仅服务器写入。每设备独立文件；listening/thinking/running 超过60秒无更新自动显示超时。设备只拉取渲染结果；Mac不参与运行。

106现有quota-mimo.timer每5分钟采集官方额度。server_integrations/server_mimo_quota.py复用服务器原有采集器及mimo_session，renewal_policy.py在HTTP401/403或业务session_expired时续期一次并重试。网络故障不轮换登录，第二次鉴权失败不循环；续期结果记录到mimo-renewal.json，采集失败保留旧值并写lastError供屏幕标记。此处是登录续期，不是付费套餐续费。
