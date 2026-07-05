# Auto-silence Codex console exes (runs on login) — v2 with PE-header patching
$base = "C:\Users\15002\AppData\Local\OpenAI\Codex"
$launcher = "$env:TEMP\silent.exe"

# PASS 1: Replace CONSOLE exes with silent launcher
Get-ChildItem $base -Recurse -Filter "*.exe" -ea 0 | Where-Object {
    $_.Name -notlike "*_real*" -and $_.Name -notlike "*silent*"
} | ForEach-Object {
    try {
        $b = [IO.File]::ReadAllBytes($_.FullName)
        if ($b.Length -gt 500) {
            $pe = [BitConverter]::ToInt32($b, 0x3C)
            if ($pe -gt 0 -and $pe -lt $b.Length - 6 -and $b[$pe + 0x5C] -eq 3) {
                $backup = Join-Path $_.DirectoryName ($_.BaseName + "_real.exe")
                if (-not (Test-Path $backup)) { Copy-Item $_.FullName $backup -Force }
                Copy-Item $launcher $_.FullName -Force
                Write-Host "LAUNCHER: $($_.Name)"
            }
        }
    } catch { }
}

# PASS 2: Patch _real.exe PE headers CONSOLE(3) -> GUI(2)
Get-ChildItem $base -Recurse -Filter "*_real.exe" -ea 0 | ForEach-Object {
    try {
        $b = [IO.File]::ReadAllBytes($_.FullName)
        $pe = [BitConverter]::ToInt32($b, 0x3C)
        $subsys = [BitConverter]::ToUInt16($b, $pe + 0x5C)
        if ($subsys -eq 3) {
            [IO.File]::WriteAllBytes($_.FullName, $b)  # unlock file
            $b = [IO.File]::ReadAllBytes($_.FullName)
            $b[$pe + 0x5C] = 2; $b[$pe + 0x5D] = 0
            [IO.File]::WriteAllBytes($_.FullName, $b)
            Write-Host "PE-PATCH: $($_.Name) 3->2"
        }
    } catch { }
}
