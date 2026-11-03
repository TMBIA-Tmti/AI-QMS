<#
.SYNOPSIS
  Snapshots LM Studio logs into logs/sessions/lmstudio/ (one <date>_lmstudio.md per day).
  Sources:
    1. ~/.lmstudio/server-logs/YYYY-MM/YYYY-MM-DD.N.log   (current LM Studio versions)
    2. %APPDATA%/LM Studio/logs/main.log                   (legacy / app log, today only)
  Back-fills every past day that has no snapshot yet, and refreshes today's.
  Skips gracefully if LM Studio has no logs.
  Called by snapshot_service_logs.ps1 on session end; safe to run manually.
#>

$projectDir = Split-Path -Parent $PSScriptRoot
$outputDir  = Join-Path $projectDir "logs\sessions\lmstudio"
$serverRoot = Join-Path $env:USERPROFILE ".lmstudio\server-logs"
$legacyLog  = Join-Path $env:APPDATA "LM Studio\logs\main.log"
$today      = Get-Date -Format "yyyy-MM-dd"

# date -> list of server log files
$byDate = @{}
if (Test-Path $serverRoot) {
    Get-ChildItem $serverRoot -Recurse -File -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match '^(\d{4}-\d{2}-\d{2})\.') {
            $d = $Matches[1]
            if (-not $byDate.ContainsKey($d)) { $byDate[$d] = @() }
            $byDate[$d] += $_
        }
    }
}

# legacy main.log lines for today (format: [yyyy-MM-dd HH:mm:ss.mmm])
$legacyToday = @()
if (Test-Path $legacyLog) {
    $legacyToday = @(Get-Content $legacyLog -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -match "^\[$today" })
    if ($legacyToday.Count -gt 0 -and -not $byDate.ContainsKey($today)) { $byDate[$today] = @() }
}

if ($byDate.Count -eq 0) { exit 0 }
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }

foreach ($date in ($byDate.Keys | Sort-Object)) {
    $outputFile = Join-Path $outputDir "${date}_lmstudio.md"
    $files = @($byDate[$date] | Sort-Object Name)

    # Past days are immutable: skip when a snapshot already exists and is newer than its sources
    if ($date -ne $today -and (Test-Path $outputFile)) {
        $newest = ($files | Measure-Object LastWriteTime -Maximum).Maximum
        if ($newest -and (Get-Item $outputFile).LastWriteTime -ge $newest) { continue }
    }

    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add("# LM Studio Server Log - $date")
    $md.Add("")
    $md.Add("- **Exported**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    foreach ($f in $files) { $md.Add("- **Source**: ``$($f.FullName)``") }
    if ($date -eq $today -and $legacyToday.Count -gt 0) { $md.Add("- **Source**: ``$legacyLog`` ($($legacyToday.Count) entries)") }
    $md.Add("")
    $md.Add("---")
    foreach ($f in $files) {
        $md.Add("")
        $md.Add("## $($f.Name)")
        $md.Add("")
        $md.Add('```')
        foreach ($line in (Get-Content $f.FullName -Encoding UTF8 -ErrorAction SilentlyContinue)) { $md.Add($line) }
        $md.Add('```')
    }
    if ($date -eq $today -and $legacyToday.Count -gt 0) {
        $md.Add("")
        $md.Add("## main.log")
        $md.Add("")
        $md.Add('```')
        foreach ($line in $legacyToday) { $md.Add($line) }
        $md.Add('```')
    }
    $md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
}
