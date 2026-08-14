# P6 稳定性、打包与回归

`config/stability.json` 保存置信度阈值、并行度、连续不变帧上限以及设备/页面 profile。`DeviceProfile.scale_bbox` 将逻辑坐标缩放并裁剪到当前分辨率；页面样式可单独覆盖区域。

`OcrDictionary` 只在给定候选标签集合内应用安全混淆（例如 `8 -> B`）。候选集合缺失或映射不唯一时返回原文和原因，不静默改写。`recognize_region` 只裁剪选中区域进行局部重 OCR，并保留原始图片。

性能可以通过 `packages.stability.timing.timed` 采集阶段耗时。Windows 构建脚本为 `scripts/build_windows.ps1`，会运行测试、编译检查、PyInstaller 收集、Paddle 原生库/元数据收集、安装器自检和外层归档。更新策略为 `config/update.json`；更新默认关闭，清单与安装包必须使用 HTTPS（回环测试除外），并受响应体大小、版本格式、安装包大小、SHA-256 和原子下载限制。

在交付前执行：

```powershell
python scripts/generate_golden_catalog.py
python -m pytest -q -p no:cacheprovider
python scripts/verify_paddle_ocr.py
./scripts/build_android.ps1
./scripts/build_windows.ps1
```

真实 PaddleOCR 回归会运行时绘制中文 PNG，从像素识别用户答案、正确答案和官方解析，不读取 sidecar。Windows 上默认关闭 MKLDNN，以规避 PaddleOCR 3.7.0/PaddlePaddle 3.3.1 的 oneDNN PIR 属性转换异常。Android 真机交互仍需要用户本人授予系统权限；离线门禁不会伪装真机授权结果。
