# USB Consent Implementation Plan

Goal: 本地屏幕确认后才枚举 HID，每次启动默认 CDC。

1. 编写独立 C++ 确认时序测试，先验证失败，再实现策略头文件。
2. 增加 CDC-only 与 CDC+HID 描述符及 RAM 模式状态；USB/CDC重建由单个任务执行。
3. 生成本地确认页，接入三页导航与绘制完成后的实体按键授权；停止撤销权限。
4. 增加 SAFE/REBOOT/BOOTLOADER 恢复命令，避免任何串口开启 HID 的路径。
5. 运行策略测试、既有测试与 ESP-IDF 编译；记录硬件未验证项。
6. 若板子可连接，先读取恢复固件心跳再验证安全固件；未连接时保留构建，不宣称刷写成功。
