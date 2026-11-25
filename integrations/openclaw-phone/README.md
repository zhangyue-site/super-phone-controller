# 微信手机控制交接 · 2026-11-25

目标是让用户在微信私聊给龙虾发指令，由 OpenClaw 绑定会话和目标设备，Dsh 规划下一步，手机本地 OCR 读取画面，ESP32 通过 USB HID 操作。执行器按新画面和板端回执核对结果。ADB 用于已授权设备的诊断和兜底。

## 代码入口

| 要接手的部分 | 从哪里开始 |
| --- | --- |
| 微信收件、预览、确认、去重 | [微信入口](weixin-intake.mjs) 和 [合成消息测试](weixin-intake.test.mjs) |
| 从桌面定位应用、核对当前画面 | [桌面观察](launcher/launcher_check.py) 和 [只读范围及结果生成](view/current_view.py) |
| 云端规划 | [Dsh 规划器](dsh/planner/worker.py) 和 [配置片段](dsh/planner/planner.patch.yml) |
| 监督执行 | [任务回执工具](dsh/review-task) 的 `--receipts <任务编号>` 读取终态和动作回执，无需模型复述。调用方沿用既有服务的身份绑定和访问配置。 |
| 手机客户端 | [Android 98 构建源码](https://github.com/zhangyue-site/super-phone-controller/tree/cd3e631eb1a9688caab84444c4e99481e54c78dd/app) 和 [GitHub 构建](https://github.com/zhangyue-site/super-phone-controller/actions/runs/45351170224) |

## 已验证到哪一步

- **用户真实微信指令。** 11 月 24 日，用户在已绑定私聊发送「请帮我打开设置」并确认，板端执行一次 HOME，任务终态回传同一私聊。共享中断前没有取得设置首页证据。独立的 ADB 测试验证了系统设置和助手间的往返。
- **监督端发起的真机只读。** 同日从正式网关向已绑定的小米 17 Ultra 发起只读任务。板子领取，终态为 `done`、`verified=true`。最后一帧本地 OCR 有 21 行，核对到「屏幕共享中」，有一条 `read_record` 回执，物理输入为零。整次约 86 秒，其中三次重新观察。随后更新的回复逻辑用这笔任务的留存帧做了回放。106 对应的发布回执版本为 `v20261124203847_f01abbca`。[当时的云端构建](https://github.com/zhangyue-site/super-phone-controller/actions/runs/45395321889)
- **手机安装与听写。** 11 月 24 日已在上述小米读回 Android 1.4.18（98）。「用原键盘听写」会切回原输入法，再点原键盘的麦克风。独立测试机验证了切换和保留编辑草稿，小米实人普通话听写仍待验收。
- **本次交接的候选改动。** 微信入口支持计算器、日历、带空格的英文应用名，以及能完整解析的打开、读取、回桌面组合。复合任务预览保留用户原话。打开应用和验证首页是两个步骤。候选代码的测试使用合成私聊和模拟派发，正式微信到应用首页的验收仍待执行。

## 如何复测

从仓库根目录执行以下命令。测试使用合成数据，可以脱离手机和服务账号运行。

```sh
node --test integrations/openclaw-phone/weixin-intake.test.mjs
python3 -B -m unittest discover -v -s integrations/openclaw-phone/launcher
python3 -B -m unittest discover -v -s integrations/openclaw-phone/view
python3 -B -m unittest discover -v -s integrations/openclaw-phone/dsh
python3 -B -m unittest discover -v -s integrations/openclaw-phone/dsh/planner
```

1. **先验通用打开。** 核对 GitHub 候选和 106 加载的模块版本。用已绑定的测试手机，在空闲且共享可用时，从本人私聊发送「请帮我打开计算器」。确认目标手机和动作后，按同一任务编号核对一次派发、板端领取与回执、操作后的计算器首页，以及原私聊收到的结果。再换一个应用复测。检查应用名始终用作目标标签，打开应用的授权范围只覆盖导航和首页核验。
2. **再验读取与保存。** 先测「打开计算器，然后汇总当前页面」。分别从支付宝和微信各取一条用户授权的记录，核对日期、金额和目标账本。保存后重新进入阿柴账本核对明细，再用同一条记录重试验证去重。结果不明时先查原回执及账本，避免重复写入。
3. **复测锁屏和重连。** 分别记录亮屏、锁屏和解锁后的客户端心跳、板端心跳、画面共享状态，以及 AI 调用的起止时间。无任务时也要测客户端在线状态。已观察到 BLE 维护心跳间歇失败，以及固件 0.6.48 下载后重启回到 0.6.47。自动更新保持开启，原因仍待定位。锁屏和受保护页面按系统授权处理。
4. **验证平台与速度。** iPhone 另验授权镜像、HID、应用首页和回传。新的本地小模型逐个接入，同一任务对照识别准确率、用时、云端调用次数和重试次数。安卓回执只计入对应设备的结果。

构建在 GitHub 完成，正式发布由 106 执行。私聊原文记录、配对凭据、账务明细和运行时配置由部署方本地保管。
