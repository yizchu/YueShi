@echo off
setlocal
title YueShi Demo
cd /d "%~dp0"
echo ==========================================
echo YueShi Demo - http://localhost:3210
echo ==========================================
set "YUESHI_NODE=node"
if exist "D:\node.exe" set "YUESHI_NODE=D:\node.exe"
"%YUESHI_NODE%" --version
if errorlevel 1 goto missing_node
"%YUESHI_NODE%" --env-file-if-exists=.env tools/launch.mjs
set "YUESHI_EXIT=%ERRORLEVEL%"
echo.
echo If no browser appeared, double-click OPEN-WEB.url
echo or enter http://localhost:3210 in your browser.
echo.
if not "%YUESHI_NO_PAUSE%"=="1" pause
exit /b %YUESHI_EXIT%
:missing_node
echo Node.js was not found. Please reinstall Node.js LTS.
if not "%YUESHI_NO_PAUSE%"=="1" pause
exit /b 1
