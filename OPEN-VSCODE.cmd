@echo off
setlocal
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" (
  start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" --new-window "%CD%"
) else (
  call code --new-window "%CD%"
)
