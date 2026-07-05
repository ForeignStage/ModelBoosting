$log = "C:\Users\15002\Desktop\proc_monitor.log"
$seen = @{}
Get-Process | % { $seen[$_.Id] = $true }
"[MONITOR] Started at $(Get-Date -Format 'HH:mm:ss')" | Out-File $log

while($true) {
  try {
    Get-Process -ea 0 | % {
      if(!$seen[$_.Id]) {
        $seen[$_.Id]=$true
        $p = try{$_.Path}catch{""}
        if($p -and $p -like "*AppData*Local*") {
          "$(Get-Date -Format 'HH:mm:ss') PID=$($_.Id) $($_.ProcessName) | $p" | Out-File $log -Append
        }
      }
    }
    $alive = (Get-Process -ea 0).Id
    $seen.Keys | ? {$_ -notin $alive} | % { $seen.Remove($_) }
  } catch {}
  sleep 2
}
