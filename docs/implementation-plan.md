# 实施计划与完成状态

## 不可妥协的数据边界

每道已作答客观题必须同时保存：题干、用户答案、粉笔正确答案、粉笔官方解析、作答结果和可回溯原始截图。缺少任一官方字段或证据时进入 `NEEDS_REVIEW`，不能导出为已验证数据；AI 只能写入独立的 `ai_analysis` 字段。

## 阶段状态

| 阶段 | 交付物 | 状态 |
|---|---|---|
| P0 | Monorepo、模型、Schema、SQLite、Windows/Android 骨架、Golden 基线 | 已完成 |
| P1 | 图片导入、OCR 适配器、结构化解析、人工校对、JSON/Markdown | 已完成 |
| P2 | 可注入 ADB、原始 PNG、页面变化检测、暂停/恢复、CLI/GUI | 已完成 |
| P3 | 统计、知识点和错误标签、错题筛选、PDF/HTML 组卷 | 已完成 |
| P4 | Android MediaProjection、前台服务、浮窗、任务检查点、LAN/USB 传输 | 已完成 |
| P5 | AI 适配器、五类 Prompt、缓存、趋势/策略/复习计划、费用统计 | 已完成 |
| P6 | 分辨率/页面配置、OCR 字典、局部重识别、计时、构建/更新配置、文档和回归 | 已完成 |

## 阶段验收要点

### P0/P1

- Mock OCR 不访问网络，真实 PaddleOCR 通过接口注入。
- `packages.core.integrity.assess_question` 在持久化前运行。
- 导出器只读取结构化字段，原始截图路径和区域证据随题目保存。

### P2

- Real/Fake ADB 使用参数列表调用，不经过 shell 拼接。
- 连续帧用 SHA-256 判断页面是否变化；达到安全停止条件时保存当前帧并停止。
- 无设备、授权失败、传输错误都返回可恢复状态，不伪造题目。

### P3

- `packages.analysis` 先做确定性统计，再提供错误标签和 wrong/risk/special/repeated selectors。
- `packages.paper_builder` 维持原题序，不重排选项。
- 空白卷不出现答案或解析；答案与解析册使用题目中的粉笔官方字段，缺字段的题目明确标记待校对。

### P4

- Android 端使用用户授权的 MediaProjection 和 `FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION`。
- 每帧落盘后更新 `CaptureSessionState.lastSequence` 和 SHA-256，进程中断可恢复。
- AUTO 失败只回退到 SEMI_AUTO；浮窗操作由用户显式触发，不包含绕过登录或风控的操作。

### P5

- Prompt 明确分离 `OFFICIAL_SOURCE` 与 `USER_AND_HISTORY`。
- 缺官方答案/解析不调用模型；模型尝试写入官方字段时剥离并标记 `NEEDS_REVIEW`。
- 缓存键包含输入哈希、模型、Prompt 版本和分析类型；重复输入不重复计费。

### P6

- `config/stability.json` 保存设备比例、页面配置、置信度阈值和并行度。
- OCR 字典只在候选标签范围内纠正，无法确定时保留原文并给出原因。
- `region_recognition` 只重识别选中区域，保留原图。
- `scripts/build_windows.ps1` 和 `config/update.json` 为打包与更新提供可审计配置；Android 构建依赖说明见 `docs/p4-android-capture.md`。

## 质量门

```powershell
python scripts/generate_golden_catalog.py
python -m pytest -q -p no:cacheprovider
```

Golden 目录包含旧基线和 16 个新增离线场景，共 23 个场景，覆盖普通/多选/判断/未答/对错/材料/长题干/长解析/图形/表格/多图/折叠解析/四屏/题号失败/重复帧/网络错误/系统弹窗/OCR 混淆/中断恢复/答案冲突。

当前全量回归为 63 个测试通过。真实 Android APK 需要本机 Android SDK 和已缓存 Gradle 依赖；在无依赖环境中仍可运行全部 Python 合同测试和 FakeAdb 流程。
