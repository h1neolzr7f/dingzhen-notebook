# P4 Android 采集伴侣

`apps/android-capture` 是一个可离线工作的 Android 采集端。用户明确授权
`MediaProjection` 后，应用通过前台服务把整屏 PNG 按序写入应用私有目录：

```text
files/capture_sessions/<task-id>/000000.png
files/capture_sessions/<task-id>/000001.png
```

每张图片落盘后立即计算 SHA-256，并将 `lastSequence`、路径和校验和写入
SharedPreferences。进程被系统回收或传输中断时，桌面端可以从检查点继续，原始截图
不会被覆盖或丢弃。

采集进度 `lastSequence` 与传输进度 `lastTransferredSequence` 分开记录，因此可以在
手机继续采集的同时暂停/恢复电脑端传输。

## 模式与安全边界

- **手动**：用户自行翻页，浮窗提供截图、题目/解析标记、重试、跳过、暂停和停止。
- **半自动**：用户确认翻页，采集端负责节流、重复帧过滤和按序保存。
- **自动**：无障碍服务只读取可见节点和已知语义锚点。用户答案、正确答案、官方解析、解析页末尾四项齐全后才点击下一题；登录页、弹窗、网络错误、题号缺失或连续三次页面不变会立即暂停。

浮窗和自动模式分别需要用户在系统设置中授予悬浮窗、无障碍权限；屏幕录制每次由系统授权。通知、网络和前台服务权限都在
`AndroidManifest.xml` 中显式声明。LAN 传输逐帧 POST 并带 SHA-256，USB 传输复用同一
检查点协议；两者均可从最后一个成功序号恢复。LAN 请求还带 HMAC-SHA256、时间戳和一次性共享密钥。HTTPS 可用于任意主机；明文 HTTP 只允许回环或 RFC1918 私网地址，且必须先用桌面端生成的 `FENBI1|地址|密钥` 配对。公网 HTTP 会被拒绝。服务器必须返回匹配的校验确认，全部帧传完后手机再 POST `/capture/<task>/complete`。

## 构建与导入

在具备 Android SDK、Gradle 依赖缓存的机器上执行：

```powershell
cd apps/android-capture
.\gradlew.bat testDebugUnitTest assembleRelease
```

当前发布包已附带构建产物：`artifacts/android/fenbi-capture-1.2.0.apk`（与 `fenbi-capture-personal-release.apk` 相同）。它使用 v2 APK 签名和 Android debug 证书，只用于个人侧载。生产签名需同时设置 `FENBI_ANDROID_KEYSTORE`、`FENBI_ANDROID_KEYSTORE_PASSWORD`、`FENBI_ANDROID_KEY_ALIAS`、`FENBI_ANDROID_KEY_PASSWORD` 后重新构建。

没有网络或依赖缓存时，仍可使用桌面端的 `packages.capture` FakeAdb/导入路径；本仓库的
P4 合同测试不依赖 Android SDK。Android APK 不会自动登录粉笔，也不会把账号密码写入
任务文件。
