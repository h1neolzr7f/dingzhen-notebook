## 单题错因分析（P5 v1）

只分析用户的作答行为与学习推断。`OFFICIAL_SOURCE` 中的粉笔正确答案、
粉笔官方解析和粉笔知识点是只读证据；不要把任何 AI 内容写回这些字段。

重点回答：用户为什么会选这个选项、遗漏了什么条件、哪个选项诱因最强、
怎样用更短路径得到答案、应如何复习。证据不足时使用 `needs_review`，不要
把原因武断归为“粗心”。

输出 `ai_fields`：`error_labels`、`error_cause`、`missed_condition`、
`choice_trap`、`correct_method`、`faster_method`、`memory_rule`、
`related_history`、`review_advice`、`controversy_note`。
