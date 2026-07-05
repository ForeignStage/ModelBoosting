@echo off
:: Register AgentHub FSWatcher as Windows login startup task
:: Run ONCE as Administrator to install; no admin needed afterwards.
schtasks /create ^
  /tn "AgentHub_DSWatchdog" ^
  /tr "pythonw \"E:\AgentHub\AgentBoosting\GodCreating\watchdog\fs_watcher.py\"" ^
  /sc ONLOGON ^
  /ru "%USERNAME%" ^
  /f
if errorlevel 1 (
    echo [FAIL] Registration failed — re-run as Administrator.
    exit /b 1
)
echo [OK] Task "AgentHub_DSWatchdog" registered. Active from next login.
echo      To remove: schtasks /delete /tn "AgentHub_DSWatchdog" /f
echo      Violations log: E:\AgentHub\AgentBoosting\GodCreating\logs\VIOLATION.log
