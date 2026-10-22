# USB 插入唤起整屏共享

用户已确认：插板子自动打开已有升级助手，弹系统整屏共享授权，确认后上传画面；复用现有App，不另装应用。用户同意的系统授权不复用，不自动刷固件或执行任务，ADB动作仍只中文输入。

Android USB_DEVICE_ATTACHED 精确列出S3当前/兼容VID=0x303a PID=4001/4005/4041/4045；运行时核对实时USB枚举、产品名Epaper Phone Controller和12位MAC序列号。只枚举身份，不打开/claim USB接口，保持NCM与HID原有职责。首次系统可能要求选择/默认打开App，这一系统行为不绕过。

首次USB配对时显示提示并由用户手动选择蓝牙板；保存USB序列号到BLE remoteId、boardInfo.device的绑定。以后同USB序列号直接连接该BLE地址，核对boardInfo.device一致后取得短期screen-frames凭证并弹系统授权；不选择最强信号或自动选择唯一附近板。没有绑定/蓝牙关闭/连接失败显示可恢复状态，不声称共享成功。

同次插入只有一次自动启动请求；重复Intent和HID切换重新枚举合并。系统拒绝、返回页面后不反复弹窗，手动共享入口保留。USB断开宽限约1.5秒后重新检查同序列号；若确认拔线，取消待处理授权、撤销能力并停止共享。重插产生新session，晚到云端授权不得启动新session。已在共享/待系统授权时重复插入不重复授权。

Dart保留USB启动session和挂载代数；Android在请求与系统授权结果时都检查USB session，避免仅靠Flutter mounted判断。Flutter ScreenShare.start对每个await检查存活，未交给原生的凭证撤销。手动BLE共享仍可用，不要求USB。

验收：Dart协议/状态/控件测试覆盖USB身份解析、初次配对、记忆板身份检查、一次启动、蓝牙关闭、断开和迟到授权；Python契约测试核对Manifest/XML与实际固件USB IDs，排除ROM及无界匹配。Android正式编译核对native实现。最终发布1.0.8+9，原签名/图标，完整下载验证。真实插拔/系统默认打开/MediaProjection确认需用户现场，不能用模拟代替。


评审补充：现有boardInfo.device是epaper-01之类逻辑ID，并非USB的MAC序列号，不能伪造两者相等校验。首次由用户显式选择蓝牙板建立关联，后续同时核对保存的BLE地址和逻辑ID；此为用户配对，不宣称首次已密码学证明USB/BLE同一设备。USB权限缺失/空序列号拒绝绑定。授权requestCode持久递增以隔离Activity重建后的迟到结果；USB session在请求授权、授权结果及服务启动三个边界验证。应用级USB拔线接收器在Activity销毁后继续保护前台共享服务，停止时清除捕获与上传并撤销能力。固件升级中不自动切换页面；HID重枚举在宽限期内合并，系统USB默认打开和全屏授权不绕过。
