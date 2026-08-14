@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 丁真笔记本
echo.
echo  丁真笔记本 1.3.4
echo  本软件不登录粉笔。请先用粉笔官方 App 登录。
echo.
if not exist "先看这个.txt" goto start
echo  第一次用请先打开「先看这个.txt」
echo.
:start
call "%~dp0start_mock.bat"
exit /b %ERRORLEVEL%
