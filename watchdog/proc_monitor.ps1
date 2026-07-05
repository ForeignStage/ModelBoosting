$logFile = "$env:USERPROFILE\Desktop\proc_monitor.log"
$seen = @{}
# Initialize with current processes
Get-Process | ForEach-Object { $seen[$_.Id] = $true }
"MONITOR STARTED $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $logFile
"Watching for new AppData\Local processes..." | Out-File $logFile -Append

while ($true) {
    try {
        $current = Get-Process -ErrorAction SilentlyContinue
        foreach ($p in $current) {
            if (-not $seen.ContainsKey($p.Id)) {
                $seen[$p.Id] = $true
                $path = try { $p.Path } catch { "" }
                if ($path -match "AppData\\Local") {
                    $line = "$(Get-Date -Format 'HH:mm:ss.fff') | PID=$($p.Id) | $($p.ProcessName) | $path"
                    $line | Out-File $logFile -Append
                }
            }
        }
        # Clean up dead PIDs
        $currentIds = $current | ForEach-Object { $_.Id }
        $dead = $seen.Keys | Where-Object { $_ -notin $currentIds }
        foreach ($d in $dead) { $seen.Remove($d) }
    } catch {}
    Start-Sleep -Seconds 2
}
