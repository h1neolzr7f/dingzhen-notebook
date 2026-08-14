# 集成测试设计

## 运行层级

1. `MockOcrEngine`：默认、离线、确定性。按样本目录读取 `expected.json`，用于验证导入、完整性检查、SQLite 和导出链路。
2. 本地 PaddleOCR：可选慢测试。对同一 PNG 实际 OCR，只比较规范化文本和关键字段，不把模型下载作为默认测试前置条件。
3. 真实账号冒烟：仅由用户在官方客户端中手动执行，不进入 CI，不保存凭据，也不把真实截图提交到仓库。

## P0/P1 集成链路

```text
PNG 批量导入
  → 排序/哈希去重
  → Mock OCR 或 PaddleOCR
  → 页面适配器
  → Question 候选
  → 完整性/一致性检查
  → SQLite 幂等写入
  → 校对队列
  → JSON / AI Markdown
```

## 必测断言

- 三项来源同时存在：`user_answer`、`official_answer`、`official_explanation_md`。
- 官方答案与官方解析都能追溯到 `analysis_frames`；题干能追溯到 `question_frames`。
- 缺官方答案或官方解析时状态一定为 `needs_review`，不得静默导出。
- `is_correct` 与用户/官方答案推导不一致时，产生 `answer_result_conflict`。
- 相同字节截图重复导入只计一个唯一帧；相同题目重复导入只保留一条记录。
- 中断恢复能把前后截图合并到同一题，且不覆盖已人工校对字段。
- 网络错误页、弹窗页和不含题号的页面不能生成伪题目，但原图仍保留。
- JSON/Markdown 中官方字段与 `ai_analysis` 分栏；AI 为空时仍可导出官方内容。

## 通过标准

默认测试必须完全离线、无需环境秘密，并在临时目录创建数据库和导出文件。可选 OCR 测试使用 `pytest -m ocr` 单独运行。任何 Golden 差异都应显示字段级 diff；更新 Golden 需要人工确认，不允许测试自动覆盖 `expected.json`。

当前样本是最小 P0/P1 套件，后续应补齐长题干、长解析、材料题、多图题、四屏跨页、OCR 字形混淆和系统弹窗等覆盖项。
