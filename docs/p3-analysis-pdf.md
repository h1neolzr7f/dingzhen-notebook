# P3 分析与组卷

`packages.analysis` 只做确定性计算：总题数、作答数、正确率、模块/知识点统计、错误标签、趋势和风险分数。标签可以由用户编辑，原始题目不会被覆盖。

```python
from packages.analysis import analyze_paper, wrong_questions, special_questions
report = analyze_paper(paper, questions)
wrong = wrong_questions(questions)
knowledge = special_questions(questions, knowledge_point="资料分析")
```

`packages.paper_builder` 的 builders 接收题目对象和输出目录，返回 `PaperBuildResult`。空白题卷不渲染用户答案、正确答案、作答结果、粉笔解析或 AI 内容；答案与解析册明确展示官方字段，并保留 evidence 路径。ReportLab 可用时写 PDF，否则写同名 HTML fallback，确保离线环境仍有可读交付物。

所有导出先筛除不满足完整性要求的题目或标注 `NEEDS_REVIEW`，不会把 AI 推断当作官方答案。
