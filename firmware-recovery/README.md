# 墨水屏原生 USB 恢复诊断固件

用于ESP32-S3微雪1.54 V2的启动与USB诊断。不开启TinyUSB HID，不初始化或刷新屏幕，不启用WiFi，不读取或写入NVS。GPIO18作为PWR输入，GPIO17保持电池供电；长按PWR1.5秒关闭电池供电保持。USB仍可供电，墨水屏保留原图不代表未关机。

必须先通过官方的“按住BOOT重新上电”进入下载模式，并从USB枚举信息/芯片身份确认目标。没有USB枚举时不能从电脑刷写。带电池且当前固件无法关机时需要实际断开电池供电再上电；不要求操作不存在的RST键。

使用ESP-IDF5.5.2 `idf.py build`。沿用原始NVS、OTA和assets布局，刷写app时不覆盖NVS或assets。原板全片备份位于本机被忽略的private-backups目录。当前尚未刷入或通过实机验收。

官方说明：https://docs.waveshare.net/ESP32-S3-ePaper-1.54/FAQ/
