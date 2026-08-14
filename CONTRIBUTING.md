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
