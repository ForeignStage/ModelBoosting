@echo off
:: DeepSeek Task Gate — run before ANY file edit or shell command
:: Usage: ds_task_start.bat "task description" [watchdog_dir]
setlocal
if "%~1"=="" (
    echo Usage: ds_task_start.bat "task description" [watchdog_dir]
    exit /b 1
)
set TASK=%~1
set WD=%~2
if "%WD%"=="" set WD=%CD%\watchdog

python "E:\AgentHub\AgentBoosting\GodCreating\watchdog\deepseek_gate.py" "%TASK%" "%WD%"
if errorlevel 1 (
    echo [GATE STOP] Read docs\CLARIFY_PENDING.md, clarify intent, then re-run.
    exit /b 1
)
echo [GATE GO] Task declared. Proceed.
endlocal
