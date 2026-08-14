# P2 离线验收报告

日期：2026-08-09

## 测试命令

```powershell
python -m pytest tests/integration/test_p2_capture_controller.py -q
```

结果：P2 桌面控制器 `4 passed`，canonical ADB transport/会话/页面变化测试 `7 passed`；全量回归 `34 passed`。

## 覆盖项

| 场景 | 证据 |
| --- | --- |
| FakeAdb 逐帧截图并落盘 | `test_fake_adb_end_to_end_saves_raw_frames_and_completes` |
| 暂停、恢复、停止转发至注入服务 | `test_pause_resume_stop_are_forwarded_to_injected_service` |
| 无设备不抛栈、给出连接授权提示 | `test_no_device_is_actionable_and_does_not_raise` |
| CLI `capture` 输出 JSON 且无需真实 adb | `test_capture_cli_can_be_exercised_with_fake_adb` |

canonical ADB 层另外覆盖：设备/屏幕尺寸/密度解析、tap/swipe 参数、PNG 像素稳定哈希、三次不变安全停止、断点 manifest 原子保存与敏感元数据过滤、transport 错误进入 `ERROR`。

测试不访问粉笔、外部网络或真实设备。P2 控制器保留每一帧原始 PNG；真实设备不可用时命令返回 `3` 并处于 `no_device`，不会继续 OCR 或创建虚假题目。

全量 P0/P1 回归也应在本机执行：

```powershell
python -m pytest -q
```
