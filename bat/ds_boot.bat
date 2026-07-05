@echo off
:: H1 Anti-Amnesia Boot — run at session start before any code change
:: Usage: ds_boot.bat [project_watchdog_dir]
setlocal
set WD=%~1
if "%WD%"=="" set WD=%CD%\watchdog

echo [BOOT] Step 1: Model self-detection...
python "E:\AgentHub\AgentBoosting\GodCreating\watchdog\model_detect.py" "%WD%"

echo [BOOT] Step 2: Injecting discipline skill...
type "E:\AgentHub\AgentBoosting\GodCreating\skills\SKILL_DEEPSEEK_DISCIPLINE.md"

echo.
echo [BOOT COMPLETE] Mode: CLARIFY (default). Run ds_task_start.bat before any file edit.
endlocal
