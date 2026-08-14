# 离线 Golden 测试集

这些图片是人工生成的粉笔风格页面，不含真实题库内容、账号、Cookie 或 Token，可在断网环境中使用。每个目录的 `expected.json` 是唯一验收真值。

| 用例 | 预期 |
|---|---|
| `verified_wrong` | 用户答案 B、官方答案 C、官方解析齐全，验证通过 |
| `verified_multi_correct` | 多选答案顺序规范化后验证通过 |
| `missing_official_explanation` | 缺官方解析，进入校对队列 |
| `conflicting_result` | 答案推导为错误但页面写“正确”，进入校对队列 |
| `interrupted_resume` | 两张截图合并为同一题，恢复后验证通过 |
| `duplicate_frame` | 两个文件内容完全相同，仅计一个唯一帧 |
| `network_error` | 网络错误页不得解析成题目，并保留原图 |

模拟 OCR 可以直接读取对应 `expected.json` 的 `question` 字段；真实 OCR 回归则应对 PNG 做识别，并将规范化结果与同一文件比较。比较时允许忽略运行时生成的 ID、时间戳和置信度小数波动，但不得忽略用户答案、官方答案、官方解析、作答结果和证据路径。
