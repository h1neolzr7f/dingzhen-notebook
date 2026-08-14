@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call "%~dp0start_mock.bat"
  if errorlevel 1 exit /b 1
)
if not exist data mkdir data
if not exist exports mkdir exports
set "GOLDEN=%~dp0samples\golden\ordinary_single_choice"
if not exist "%GOLDEN%\screen_01.png" (
  echo 找不到 Golden 样本: %GOLDEN%
  exit /b 1
)
echo 运行 Mock OCR 闭环演示...
".venv\Scripts\python.exe" -m apps.desktop.main --cli --ocr-engine mock --import "%GOLDEN%\screen_01.png" --group demo-q1 --kind question --paper-id paper_demo --paper-title "演示试卷" --output exports\demo-draft.json --database data\demo-study.db
if errorlevel 1 exit /b 1
echo.
echo 生成组卷...
".venv\Scripts\python.exe" -m apps.desktop.main build-paper --paper-json exports\demo-draft.json --paper-output exports\demo_paper_bundle --paper-formats html pdf 2>nul
if errorlevel 1 (
  echo build-paper 可选步骤失败或草稿格式不同，跳过
)
echo.
echo 完成。查看:
echo   data\demo-study.db
echo   exports\demo-draft.json
echo   exports\
dir /b exports
exit /b 0
