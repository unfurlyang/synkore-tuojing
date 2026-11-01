# 涂鸦 T5 开发板

已实测硬件：T5-BOARD V102 主板、T5-BOARD-35565 LCD 触摸屏扩展板、板载麦克风与 KEY，未接喇叭。固件为2.2.0：480×320 横屏，LVGL 270°（相对原版翻转180°）。六表情、24方位图像支持主界面与互动窗口360°转身。

## 构建

使用 [TuyaOpen](https://github.com/tuya/TuyaOpen) SDK；本次实测提交 `695e571fb4f62932dbf86a86fde664fcb7f2c0b4`。安装其官方工具链。设置 `OPEN_SDK_ROOT` 指向 SDK，在本仓库 `firmware/` 中构建。

先将 `include/bridge_token.example.h` 复制为 `include/bridge_token.h`，换成你自己随机生成的至少32字节配对字符串。此文件已忽略，不能提交。Wi-Fi 在板上输入2.4GHz网络和密码。

```powershell
python "$env:OPEN_SDK_ROOT\tos.py" config set CONFIG_PROJECT_VERSION=2.2.0
python "$env:OPEN_SDK_ROOT\tos.py" build
```

烧录必须匹配 T5AI、实际 COM 口和 QIO 包，并先备份当前固件。本仓库不提供带开发者私有配对令牌的固件二进制；从公开源码用自己的令牌构建。不要全片擦除未知校准与配置分区。

## Windows 桥接

在 `%APPDATA%\Synkore\data\device-connection.json` 中保存：

```json
{"ip":"你的开发板局域网IPv4","token":"与你构建固件时相同的配对字符串"}
```

保持 Windows App 运行。电脑和板子需在同一局域网；板子 TCP 端口8765。该文件不是交付物，不要上传到仓库。

## 协议概览

固定12字节头：`T5VT`，1字节类型、3字节保留、4字节网络序长度。类型1是最多8192字节 UTF-8 JSON；类型2是16kHz单声道 PCM16LE，单次最多640000字节。先发送 `hello` 和配对令牌；服务端返回协议1及固件版本。无身份的命令被拒绝。

- `teacher_list`／`course_list`：稳定 ID、名称及 `selected_id`。每组最多4个实际选项，另有上一组／下一组导航。
- `teacher_select`／`course_select`：板上选择同步至电脑。
- `course_action`：开始所选课程；`progress`、`result` 回传进度与分页文字。
- `audio` + PCM帧 + `audio_end`：上传录音；`get_result`／`result_ack`：结果翻页与确认。
- `ping`／`pong`：心跳；`cancel`：取消；`pet_state`：幽灵状态；`get_catalog_state`：联调回读方向及选择。

完整实现以 `firmware/src/main.c` 和 `desktop/backend/app/device_link.py` 为准。局域网帧采用配对令牌，并非 TLS；不要直接转发到公网。

板上 KEY 短按开始／停止，长按取消；触摸可切模式与互动。没有喇叭，因此板端不启用播报。开发者已验证烧录、Wi-Fi、麦克风上传、文字回传与选择同步；用户已实物确认方向和触摸正常。
