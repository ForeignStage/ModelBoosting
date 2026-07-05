@echo off
:: Start FSWatcher daemon in background (minimized window)
start "AgentHub-Watcher" /min pythonw "E:\AgentHub\AgentBoosting\GodCreating\watchdog\fs_watcher.py"
echo [DAEMON] fs_watcher started.
