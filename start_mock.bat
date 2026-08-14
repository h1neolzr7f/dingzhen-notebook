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
    echo 需要 Python 3.12 x64。可用: uv python install 3.12  或  py -3.12
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -U pip wheel
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.lock
  if errorlevel 1 exit /b 1
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps -e .
  if errorlevel 1 exit /b 1
)
if not exist data mkdir data
if not exist exports mkdir exports
set "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
echo 启动丁真笔记本 1.3.4 [Mock OCR / 无需下载模型]
".venv\Scripts\python.exe" -m apps.desktop.main --ocr-engine mock
exit /b %ERRORLEVEL%
