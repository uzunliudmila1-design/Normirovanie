@echo off
chcp 65001 >nul

:: Stop old server
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5050 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a 2>nul
)

:: Clear bytecode cache
for /d /r %%d in (__pycache__) do rd /s /q "%%d" 2>nul

:: Start server in background
start /b python app.py

:: Wait until server is listening
:wait
timeout /t 1 >nul
netstat -aon 2>nul | findstr ":5050 " | findstr "LISTENING" >nul
if errorlevel 1 goto wait

start "" http://localhost:5050
echo Server is running. Press Ctrl+C to stop.
cmd /k
