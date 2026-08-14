# P5 AI 深度分析

## 适配器

- `MockAIModelAdapter`：离线、可重复、用于 CI 和 Golden。
- `CallableAIModelAdapter`：连接本地 Python 模型函数，不序列化函数。
- `LocalHTTPAIModelAdapter`：默认只允许 `127.0.0.1`/`localhost`，只发送 model/prompt/system/安全元数据，不接受认证头。

## 分析产品

`QUESTION_ERROR`、`PAPER`、`HISTORY`、`LEARNING_STRATEGY` 和 `REVIEW_PLAN` 均通过同一服务入口。确定性统计先运行，再把结果作为上下文交给模型。

每次 Prompt 都有 `OFFICIAL_SOURCE` 和 `USER_AND_HISTORY` 两个区块。官方答案和官方解析缺失时返回 `NEEDS_REVIEW` 且不调用模型；AI 输出若包含 `official_answer`、`official_explanation` 等字段会被移除并发出警告，原题官方字段保持不变。

缓存键由输入哈希、模型、Prompt 版本和分析类型组成，可使用 `FileAnalysisCache` 或 `SQLiteAnalysisCache`。`CostTracker` 记录调用次数、缓存命中、token 和费用。
