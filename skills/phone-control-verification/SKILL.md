---
name: phone-control-verification
description: Plans bounded phone-control tasks, checks fresh screen evidence, and verifies recovery and hardware receipts. Use when explicitly invoking this skill to review a phone task or run synthetic regressions.
disable-model-invocation: true
---

# 手机控制规划与核验

默认用离线样本。只有用户明确授权目标设备、任务范围及副作用，才通过现有协调服务提交真实任务。用户未授权时，输出计划和验收条件。

1. 记录目标、预期结果、允许页面和动作、截止时间、停止条件。点击、滑动与提交分别列出。遇到提交、付款或发送等外部副作用，按用户授权边界停下。
2. 通过服务获取与目标、捕获会话和当前动作关联的新画面。先判断页面及地标，再从已允许的控件中定位目标。文字、视觉区域和当前上下文互相矛盾时标记待核验。
3. 遇到已知遮挡，先定位具体遮挡和明确的关闭控件。最多建议一次已授权的恢复动作，再重新观察。列表找不到地标时，仅在方向、范围及预算明确的情况下建议有限滚动。停止、掉线、过期、回执缺失或范围不明时结束。对已经派发的动作先查状态，避免重放。
4. 同一任务的板端 ACK 只说明动作被接收。核对动作之后独立的新画面与预期结果；缺少因果对应时保留未核验。输出任务范围、动作与证据、核验结果、停止原因。证据只保留必要的脱敏摘要。
5. 协调服务处理设备身份、同意、画面接收、时效、队列、执行所有权和硬件回执。使用项目已有认证入口；保持系统投屏确认、板端本地许可和 STOP。模型识别结果只是观察证据。

## 离线演练

在公开仓库根目录安装 Pillow 和 `requirements-keyboard.txt`，再运行：

```sh
python3 tools/run_offline_tests.py test_vision_output_contract test_vision_transport test_screen_state_diagnostics test_general_nav test_readiness
```

例如，合成画面中目标被弹窗遮住时，计划应先确认关闭控件，执行后等待新画面，再重新定位。若服务仅返回 ACK，结果保持「已接收、画面未核验」。演练使用本机模拟接口、合成画面和模拟回执。
