package com.local.fenbistudy.capture

object WrongPaperHtml {
    fun render(library: StudyLibrary, onlyWrong: Boolean = true): String {
        val items = if (onlyWrong) library.questions.filter { it.isCorrect != true } else library.questions
        val grouped = items.groupBy { it.paperId }
        val body = grouped.entries.joinToString("\n") { (paperId, questions) ->
            val title = library.papers.firstOrNull { it.id == paperId }?.title ?: "未命名试卷"
            val rows = questions.sortedBy { it.sequence }.joinToString("\n") { question ->
                """
                <article class="card">
                  <h3>第${question.sequence}题 · ${escape(question.folderName)}</h3>
                  <p class="stem">${escape(question.stem.ifBlank { "（无题干）" })}</p>
                  <p><b>我的答案</b> ${escape(question.userAnswer.ifBlank { "未作答" })}</p>
                  <p><b>正确答案</b> ${escape(question.officialAnswer.ifBlank { "未采集" })}</p>
                  <p><b>解析</b> ${escape(question.explanation.ifBlank { "还没有解析" })}</p>
                  <p class="meta">${escape(question.knowledge.joinToString("、").ifBlank { "未标注知识点" })}</p>
                </article>
                """.trimIndent()
            }
            val sheet = questions.sortedBy { it.sequence }.joinToString("　") {
                "第${it.sequence}题 ${escape(it.officialAnswer.ifBlank { "—" })}"
            }
            """
            <section>
              <h2>${escape(title)}</h2>
              <p class="sheet">答题卡：$sheet</p>
              $rows
            </section>
            """.trimIndent()
        }
        return """
            <!doctype html>
            <html lang="zh-CN">
            <head>
              <meta charset="utf-8"/>
              <meta name="viewport" content="width=device-width, initial-scale=1"/>
              <title>今知错题卷</title>
              <style>
                body { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; background: #F7F3EC; color: #1F2933; margin: 0; padding: 20px; }
                h1 { color: #115E59; }
                h2 { margin-top: 28px; }
                .card { background: #fff; border: 1px solid #D6CBBA; border-radius: 16px; padding: 16px; margin: 12px 0; }
                .stem { font-weight: 600; }
                .meta, .sheet { color: #6B7280; font-size: 14px; }
              </style>
            </head>
            <body>
              <h1>今知错题卷</h1>
              <p>本机生成 · ${items.size} 题 · 可打印或发给电脑</p>
              ${body.ifBlank { "<p>还没有可组卷的题目。</p>" }}
            </body>
            </html>
        """.trimIndent()
    }

    private fun escape(value: String): String = value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
}
