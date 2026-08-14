# 安全说明

## 报告问题

请不要在公开 Issue 里粘贴：

- 粉笔 / 任何平台的账号、密码、Cookie、Token
- 真实试卷截图或完整题干
- 本机绝对路径、配对密钥、局域网地址

安全问题请用 GitHub 的 [Private vulnerability reporting](https://github.com/h1neolzr7f/dingzhen-notebook/security/advisories/new) 提交，或只描述复现步骤、不带私人数据。

## 项目边界

- 默认不申请通知权限、不扫描全部已装应用
- 局域网传输使用一次性配对码和 HMAC-SHA256，只接受私网地址
- 本地 HTTP AI 适配器默认只允许回环地址，不接受 API key / Cookie / Authorization
- Android 随附 APK 使用 debug 证书，仅适合本人侧载，不要上架应用商店
