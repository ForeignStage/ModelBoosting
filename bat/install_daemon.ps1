$taskName = "AgentHub_Constitution_Daemon"
$python = "C:\Users\15002\AppData\Local\Programs\Python\Python313\pythonw.exe"
$script = "E:\AgentHub\AgentBoosting\GodCreating\watchdog\daemon_tick.py"

$action = New-ScheduledTaskAction -Execute $python -Argument $script
$action.WorkingDirectory = "E:\AgentHub\AgentBoosting\GodCreating\watchdog"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(-1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -Hidden

try {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop
    Write-Host "SUCCESS: AgentHub Daemon installed (silent, pythonw, every 5 min)"
} catch { Write-Error "Failed: $_" ; exit 1 }
