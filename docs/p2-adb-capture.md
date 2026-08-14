# P2：USB/ADB 采集

P2 在 P1 的人工截图闭环上增加了一个可替换的电脑端采集边界。桌面端只依赖 `CaptureService` 协议，因此真实 ADB、Android 伴侣和离线 FakeAdb 都可以使用同一套暂停、恢复、停止和异常状态处理。

## CLI

在粉笔官方客户端中打开用户本人有权查看的已完成试卷后，连接已经开启 USB 调试的 Android 手机：

```powershell
python -m apps.desktop.main capture `
  --capture-output data/captures/session-001 `
  --max-frames 10 `
  --capture-interval 0.4
```

`--max-frames -1` 表示持续运行，直到用户停止进程或调用控制器的 `stop()`。每张原始 PNG 会保存到输出目录，并在标准输出打印 JSON 摘要：

```json
{
  "status": "completed",
  "frames_captured": 10,
  "output_dir": "data/captures/session-001",
  "frames": ["data/captures/session-001/000000.png"]
}
```

可以用 `--device SERIAL` 选择指定设备。未找到 `adb`、手机未连接、设备仍处于 `unauthorized` 或指定序列号不存在时，命令返回退出码 `3`，状态为 `no_device`，并打印可操作的连接/授权提示；不会进入 OCR，也不会伪造截图。

## 生命周期

`apps.desktop.capture_controller.CaptureController` 的状态为：

```text
IDLE → CONNECTING → RUNNING → COMPLETED
                    ├→ PAUSED → RUNNING
                    ├→ STOPPING → STOPPED
                    ├→ NO_DEVICE
                    └→ ERROR
```

```python
controller = CaptureController(
    service,                    # AdbCaptureService 或注入的 FakeAdb
    output_dir="data/captures",
    on_status=lambda snapshot: print(snapshot.status.value),
    on_frame=lambda frame: print(frame.path),
)
controller.start(wait=False)     # GUI 使用非阻塞模式
controller.pause()
controller.resume()
controller.stop()
controller.wait()
```

服务可以同步返回 `CaptureFrame` 可迭代对象，也可以通过 `start(on_frame=...)` 回调逐帧交付。控制器会把 `bytes` 帧落盘为 PNG，并为每帧保留序号和元数据；它不会删除任何原始帧。

## GUI

桌面端顶部的采集状态区提供“开始采集 / 暂停 / 继续 / 停止”按钮，显示状态、截图数和异常消息。采集回调在后台线程执行，状态更新排队回 Qt 事件循环，避免阻塞题目校对界面。GUI 默认使用 `AdbCaptureService`，测试或未来 Android 伴侣可通过 `MainWindow(..., capture_service=service)` 注入替代服务。

## 安全边界

- 采集只执行 `adb devices`、`adb exec-out screencap -p`，可选执行保守的 `input swipe`；不读取账号、密码、Cookie、Token 或 API Key。
- 登录和权限确认始终由用户在粉笔官方客户端中完成。
- 页面变化检测、题号识别和“题目 + 官方答案 + 官方解析”配对应由后续适配器提供；当前 P2 控制器不会在无法确认页面状态时猜测题目字段。
- 网络错误、登录页、弹窗或解析缺失应由具体服务报告为 `ERROR`/`NO_DEVICE`，并保留已经落盘的原始截图供人工处理。

## 离线验收

```powershell
python -m pytest tests/integration/test_p2_capture_controller.py -q
```

测试中的 `FakeAdb` 完全在内存中生成 1×1 PNG，不启动 adb、不访问网络，覆盖原始帧落盘、暂停/恢复/停止、无设备友好错误和 CLI JSON 摘要。
