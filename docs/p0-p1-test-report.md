# P0/P1 文档与离线测试报告

日期：2026-08-09

## 结果

- 全量测试：`23 passed`
- 集成测试：`7 passed`
- CLI Mock OCR 冒烟：通过
- CLI → SQLite → JSON/Markdown 端到端持久化：通过
- PySide6 无界面窗口初始化：通过
- Android Gradle 工程配置/任务加载（离线）：通过
- Android `assembleDebug`：本机缺少 Compose/Kotlin 依赖缓存且外网下载超时，未生成 APK；联网后运行 `gradlew.bat assembleDebug` 即可复验
- 测试网络依赖：无
- 测试账号依赖：无

CLI 冒烟使用 `samples/golden/verified_wrong/screen_01.png`，成功提取：

```json
{
  "user_answer": ["B"],
  "official_answer": ["C"],
  "official_explanation_md": "甲未通过；乙与丙结果相反且只有一人通过。结合题设可知丙通过，因此选 C。",
  "missing_required_fields": []
}
```

## Golden 覆盖

已提供 7 类用例、9 张 1080 × 1920 PNG：验证通过的错题、验证通过的多选题、缺官方解析、答案结果冲突、中断后双屏恢复、重复截图和网络错误页。每个目录都有 `expected.json`；可解析页面另带 bbox 和置信度齐全的 OCR sidecar。

## 已验证的不变量

- 用户答案、官方答案、官方解析缺一不可。
- 官方字段有原始图片及 bbox 证据。
- 缺官方解析不会被猜测补全。
- 答案与作答结果冲突会进入校对队列。
- 图片按内容哈希去重。
- SQLite 重复 upsert 不产生重复题目，官方字段往返不丢失。
- 中断后的题目页和解析页能组合成完整草稿。

## 后续扩展测试

真实页面适配稳定后，应继续补齐材料题、图形推理、表格资料分析、多图片题、长题干、长解析、四屏跨页、题号识别失败、系统弹窗以及 OCR `B/8`、`I/1` 混淆样本。真实账号冒烟只在用户本机官方客户端中手动运行，不进入默认自动测试。
