# 对照「今知错题本」的升级说明

参考站点：https://www.jinzhi.fun/correction/download

## 今知能力摘要（产品对照）

| 能力 | 今知 | 本成品（升级后） |
|------|------|------------------|
| 多端下载（Win/Mac/Android/iOS） | 有 | Windows 源码+安装包 + Android APK |
| 拍照/截图录题 | APP 拍照 | 粉笔截图 + ADB/Android 采集伴侣 |
| AI 识别题目 | 云端 AI | 本地 Mock/PaddleOCR + 可选本地 AI |
| 文件夹/章节/知识点 | 有 | 导入包保留 folder；知识点导图导出 |
| 预习/一刷/二刷/间隔复习 | 有 | `review-plan` 本地复习轨道 |
| 错题包 ZIP 导入导出 | `jinzhi-mistake-package` | **兼容导出/导入** |
| Excel 模板制包 | Web 制作器 | 可先用今知网页制包，再本机导入 |
| PDF 批注 | 有 | PDF 组卷（错题卷/答题卡/解析册） |
| 云同步/订阅 | 有 | **不做云同步**（本地优先，隐私边界） |
| 粉笔官方答案证据链 | 无 | **本产品核心优势** |

## 本轮新增命令

```powershell
# 从试卷 JSON 导出今知兼容错题包
python -m apps.desktop.main export-mistake-package `
  --paper-json exports\paper_smoke\paper.json `
  --package-zip exports\jinzhi-compatible.zip

# 导入今知错题包（或本工具导出的包）
python -m apps.desktop.main import-mistake-package `
  --package-zip exports\jinzhi-compatible.zip `
  --database data\fenbi-study.db

# 生成预习/一刷/二刷复习计划 + 知识点导图
python -m apps.desktop.main review-plan `
  --paper-json exports\paper_smoke\paper.json
```

## 兼容格式

```json
{
  "format": "jinzhi-mistake-package",
  "schema_version": 1,
  "title": "我的错题包",
  "folders": [{"id": "default", "name": "导入错题", "parent_id": null}],
  "mistakes": [],
  "media": []
}
```

媒体路径必须是 `media/文件名`，与今知网页制作器一致。
