# Changelog

## 1.3.4 — 2026-08-14

### Changed

- 手机端显示名改为「丁真笔记本」。
- 开源仓库与小白一键包：`一键开始.bat`、GitHub Actions、免责与负责任使用说明。

## 1.3.3 — 2026-08-13

### Fixed

- 只打开粉笔（`com.fenbi.android.servant`），不再打开猿题库/小猿搜题。
- 去掉通知权限、网络状态权限，以及扫描全部桌面应用的查询。

## 1.3.2 — 2026-08-13

### Changed

- 自动翻页改成点一下进入开关页；打开开关返回后自动继续采集。
- 进入系统设置时显示顶部提示条，只提醒打开「今知自动翻页」。

## 1.3.1 — 2026-08-13

### Changed

- 小米自动翻页改成轮椅引导：直接尝试打开「今知自动翻页」开关页，并写明在无障碍最底下的「已下载的服务」里找。
- 找不到权限时可一键改成「我自己翻」，照常采集。

## 1.3.0 — 2026-08-13

### Added

- 手机端做成完整错题本：首页、收题、错题、复习、我的。
- 本机导入/导出今知错题包，复习轨道与桌面一致。
- 错题搜索、分卷/分类/知识点筛选、校对、复习会话、错题卷 HTML。

## 1.2.2 — 2026-08-13

### Changed

- 手机端按今知错题本风格重做：三步收题、权限清单、模式卡片、主按钮；悬浮窗收成精简控制条。

## 1.2.1 — 2026-08-13

### Changed

- 本软件不登录粉笔、不要账号密码。开始采集后直接回到已经安装并登录的粉笔 App。
- 去掉「确认已登录」对话框；登录页只等待，不会自动填写或点击登录。

## 1.2.0 — 2026-08-13

### Added

- 桌面端 LAN 接收：生成 `FENBI1|地址|密钥` 配对码，手机传到电脑后自动 OCR 并进入校对。
- CLI：`receive-lan`。
- 粉笔页面标记统一到 `config/page_markers.json`，Android 资源同步一份。
- 产品版本号统一为 1.2.0（桌面 / 手机 / 更新配置）。

### Changed

- 手机伴侣允许同一局域网的 HTTP（仍要求 HMAC 配对；公网 HTTP 拒绝）。
- 传完后补发 `/capture/<task>/complete`，电脑据此收尾。

## 1.1.1 — 2026-08-13

### Fixed

- Android 自动采集：登录后等待而不是报错退出；只操作粉笔 App；不再把「取消」当成弹窗。
- 桌面采集默认持续拍摄，不再拍 1 张就组卷；每套卷使用独立试卷编号。
- 答案按 A–H 解析；错题包 ZIP 增加体积门禁；本地 AI 只允许模型 API 路径。
- 桌面改为收题 / 校对 / 导出三步中文向导。

## 1.1.0 — 2026-08-10

### Added（对照今知错题本 https://www.jinzhi.fun/correction/download）

- 今知兼容错题包 `jinzhi-mistake-package` v1：`export-mistake-package` / `import-mistake-package`
- 复习轨道：预习 / 一刷 / 二刷 / 间隔复习（`review-plan`）与知识点 Markdown 导图
- 启动脚本：`start_mock.bat`、`start_cli_demo.bat`；`start_windows.bat` 支持 mock 回退
- 文档：`使用说明-交付.md`、`docs/jinzhi-upgrade.md`

### Fixed

- `packages/analysis/analyzer.py` f-string 反斜杠兼容性

### Verified

- 全量 pytest 通过；CLI 导入/组卷/错题包往返/复习计划通过

## 1.0.0 — 2026-08-09

### Added

- P0/P1：Windows 桌面端、Mock/PaddleOCR 接口、完整性状态机、SQLite、JSON/Markdown 导出。
- P2：Real/Fake ADB、原始 PNG、页面变化检测、暂停/恢复、CLI/GUI 采集控制器。
- P3：统计、知识点与错误标签、错题/风险/专项/重复筛选、空白错题卷、答题卡、答案与解析册 PDF/HTML。
- P4：Android MediaProjection、前台服务、浮窗、任务检查点、LAN/USB 可恢复传输和自动失败回退。
- P5：Mock/Callable/本地 HTTP AI 适配器，五类分析 Prompt，文件/SQLite 缓存和费用统计。
- P6：设备/页面配置、OCR 字典、局部重识别、计时工具、Golden 目录生成器、Windows 构建和更新配置。
- Android 无障碍安全自动翻页、感知哈希去重/暂停门禁、可拖动多操作浮窗和 HMAC-SHA256 LAN 传输。
- Windows 校验型安装器、完整 Paddle/PaddleX 打包、真实中文像素 OCR 冒烟、崩溃日志和 SHA-256 更新下载。
- 23 个离线 Golden 场景及 Android/P3/P5/P6 行为/集成测试；全量 72 tests passed。

### Safety

- 用户答案、粉笔正确答案、粉笔官方解析和原始证据分开保存；缺字段进入 `NEEDS_REVIEW`。
- AI 不得猜测、覆盖或伪装粉笔官方字段；模型输出中的官方字段会被剥离。
- 默认不访问网络、不保存账号密码、Cookie、Token 或 API key；本地 HTTP AI 默认只允许回环地址。

## 0.1.0 — 2026-08-09

- 初始 P0/P1 版本，包含离线 Mock OCR、结构化题库、人工校对、Golden 基线和用户指南。
