@echo off
schtasks /Delete /TN "AgentHub_Constitution_Daemon" /F 2>nul
schtasks /Create /TN "AgentHub_Constitution_Daemon" /XML "E:\AgentHub\AgentBoosting\GodCreating\bat\_task_def.xml" /F
echo RC=%ERRORLEVEL%
