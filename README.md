# 超级手机控制器

目标：手机不安装应用、不启用安卓无障碍服务，使用系统投屏获取画面，通过 ESP32-S3 USB HID 控制手机；日常使用脱离 Mac。优先验证小米 17 Ultra、小米 9、Civi 3，并适配 iPhone。

## 当前实际状态

- `firmware/`：原型按钮、麦克风初始化和灯效；尚未实现采音和 HID。
- `coordinator/sessions.py`：多设备独立绑定、画面新鲜度检查、指令过期与一次性消费；8 项单元测试通过。它不提供网络认证、图像采集或实际控制。
- `host/phone_wifi.py`：历史 Mac 配网辅助，不属于最终运行链路。密码从环境变量或钥匙串读取。
- `reference/`：不完整的历史参考，依赖原环境，不可直接部署。

尚未完成投屏接收、HID、语音识别、视觉决策和多机实测。没有声称任何手机已兼容。

## 无应用方案的待定硬件

手机不装采集应用时，候选为独立 Linux 接收盒：安卓 Miracast，iPhone AirPlay。每部受控手机连接一块独立 USB HID 板；采集源与板子必须显式配对。是否接受接收盒仍待确认。

Miracast 多路并发受网卡、驱动和 Wi-Fi Direct 组合限制；必须先验证单路，再评估多网卡或独立接收通道。不能假定单网卡支持多部。iPhone 鼠标需开启系统 AssistiveTouch；屏幕共享需用户启动。受保护画面可能无法采集。

当前 AtomS3U 无 PSRAM，不承担完整无线投屏接收或本地视觉模型。仅靠现有小板且不增加接收端，完整目标尚无已验证方案。

## 验证

在仓库目录执行：

```sh
python3 -m unittest discover -s tests -v
```

## 参考

- https://github.com/espressif/esp-idf/tree/master/examples/peripherals/usb/device/tusb_hid
- https://github.com/FDH2/UxPlay
- https://github.com/albfan/miraclecast
- https://github.com/Genymobile/scrcpy

仅列为调研参考，尚未合入其代码。引入时保留并遵守各自许可证。
