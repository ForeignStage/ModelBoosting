@echo off
:: Auto Mode Loop — runs auto_executor until fuse blown.
:: Usage: auto_loop.bat codex|claude_code [project_root]
setlocal
set AGENT=%~1
set ROOT=%~2
if "%AGENT%"=="" set AGENT=codex
if "%ROOT%"=="" set ROOT=%CD%
:loop
python "E:\AgentHub\AgentBoosting\GodCreating\watchdog\auto_executor.py" --agent %AGENT% --mode auto "%ROOT%"
if %ERRORLEVEL%==3 (echo [LOOP] FUSE BLOWN. & goto :end)
if %ERRORLEVEL%==1 (timeout /t 30 >nul)
timeout /t 5 >nul
goto :loop
:end
endlocal
