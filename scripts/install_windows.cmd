@echo off
setlocal
set "TARGET=%LOCALAPPDATA%\FenbiStudy"
set "APPDIR=%TARGET%\app"
if not exist "%TARGET%" mkdir "%TARGET%"
if exist "%APPDIR%" rmdir /s /q "%APPDIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%CD%\FenbiStudy.zip' -DestinationPath '%APPDIR%' -Force"
if errorlevel 1 exit /b 1
if not exist "%TARGET%\config" mkdir "%TARGET%\config"
copy /y "%CD%\update.json" "%TARGET%\config\update.json" >nul
copy /y "%CD%\stability.json" "%TARGET%\config\stability.json" >nul
copy /y "%CD%\uninstall_windows.cmd" "%TARGET%\uninstall_windows.cmd" >nul
if not exist "%TARGET%\data" mkdir "%TARGET%\data"
if not exist "%TARGET%\exports" mkdir "%TARGET%\exports"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Programs')+'\粉笔学习数据处理系统.lnk');$s.TargetPath='%APPDIR%\FenbiStudy.exe';$s.WorkingDirectory='%TARGET%';$s.Save()"
start "" "%APPDIR%\FenbiStudy.exe"
exit /b 0
