@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where uv >nul 2>nul
  if not errorlevel 1 (
    uv venv --python 3.12 .venv
  ) else (
    py -3.12 -m venv .venv
  )
  if errorlevel 1 (
    echo 需要 Python 3.12 x64。
    echo 推荐: uv python install 3.12
    echo 或安装官方 Python 3.12 后使用 py -3.12
    echo.
    echo 若只想先试用界面、不下载 OCR 模型: 运行 start_mock.bat
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -U pip wheel
)
if /I "%~1"=="mock" goto mock
if /I "%FENBI_OCR_ENGINE%"=="mock" goto mock

echo 安装/更新核心依赖与 PaddleOCR（首次较慢）...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-ocr.lock
if errorlevel 1 (
  echo OCR 依赖安装失败。可先运行 start_mock.bat 使用 Mock OCR。
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps -e .
if errorlevel 1 exit /b 1
if not exist data mkdir data
if not exist exports mkdir exports
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
echo 启动丁真笔记本 1.3.4 [真实 PaddleOCR]
".venv\Scripts\python.exe" -m apps.desktop.main --ocr-engine paddle
exit /b %ERRORLEVEL%

:mock
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.lock
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps -e .
if errorlevel 1 exit /b 1
if not exist data mkdir data
if not exist exports mkdir exports
echo 启动粉笔学习整理 1.2.1 [Mock OCR]
".venv\Scripts\python.exe" -m apps.desktop.main --ocr-engine mock
exit /b %ERRORLEVEL%
