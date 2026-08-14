@echo off
setlocal
del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\粉笔学习数据处理系统.lnk" 2>nul
echo 用户数据位于 "%LOCALAPPDATA%\FenbiStudy\data"，卸载不会自动删除。
echo 如需删除程序文件，请关闭本窗口后手动删除 "%LOCALAPPDATA%\FenbiStudy"。
pause
