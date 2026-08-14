# 参与贡献

感谢你愿意改进丁真笔记本。

## 开始前

1. 阅读 [DISCLAIMER.md](DISCLAIMER.md) 和 [RESPONSIBLE_USE.md](RESPONSIBLE_USE.md)。
2. 不要提交真实试卷、账号、Cookie 或本机数据库。
3. 测试请用 `samples/golden/` 里的合成数据，或自己造的假题。

## 本地开发

需要 Python 3.12：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Android 工程在 `apps/android-capture`，需要 JDK 17 与 Android SDK：

```powershell
cd apps\android-capture
.\gradlew.bat testDebugUnitTest
```

## 欢迎的改动

- 小白说明、Windows 一键启动、小米权限引导
- 只打开粉笔、不打开猿题库 / 小猿搜题的防护
- 校对、复习轨道、今知错题包兼容
- 测试与回归

## 不接受的改动

- 登录粉笔、保存 Cookie、自动填账号
- 绕过付费或未授权内容
- 把无障碍服务扩到任意 App

## 怎么提

- 缺陷用 [Bug 模板](https://github.com/h1neolzr7f/dingzhen-notebook/issues/new?template=bug_report.yml)
- 建议用 [功能模板](https://github.com/h1neolzr7f/dingzhen-notebook/issues/new?template=feature_request.yml)
- 安全问题走 [SECURITY.md](SECURITY.md)，不要在公开 Issue 里贴私人数据
- Pull Request 请说明为什么改、改了什么，并勾选模板里的检查项
