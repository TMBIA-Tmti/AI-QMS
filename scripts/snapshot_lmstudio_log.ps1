<#
.SYNOPSIS
  Snapshots the LM Studio log lines written WHILE THIS PROJECT WAS RUNNING into
  logs/sessions/lmstudio/ (one <date>_lmstudio.md per day).

  A project run window = [start stamp in logs/chainlit/<stamp>_chainlit.log or
  <stamp>_console.log, that file's last write time]. LM Studio activity outside
  these windows (other apps, other projects) is NOT exported.

  LM Studio sources:
    1. ~/.lmstudio/server-logs/YYYY-MM/YYYY-MM-DD.N.log   (current versions)
    2. %APPDATA%/LM Studio/logs/main.log                   (legacy / app log)
  Past days are written once; today's snapshot is refreshed on every call.
  Called by snapshot_service_logs.ps1 on session end; safe to run manually.
#>

$projectDir = Split-Path -Parent $PSScriptRoot
$outputDir  = Join-Path $projectDir "logs\sessions\lmstudio"
$chainDir   = Join-Path $projectDir "logs\chainlit"
$serverRoot = Join-Path $env:USERPROFILE ".lmstudio\server-logs"
$legacyLog  = Join-Path $env:APPDATA "LM Studio\logs\main.log"
$today      = Get-Date -Format "yyyy-MM-dd"
$culture    = [Globalization.CultureInfo]::InvariantCulture

# --- project run windows -------------------------------------------------------
$windows = @()
if (Test-Path $chainDir) {
    Get-ChildItem $chainDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_(chainlit|console)\.log$' } |
        ForEach-Object {
            $s = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd_HH-mm-ss', $culture)
            $e = $_.LastWriteTime
            if ($e -lt $s) { $e = $s }
            $windows += [pscustomobject]@{ Start = $s; End = $e.AddSeconds(5) }
        }
}
if ($windows.Count -eq 0) { exit 0 }

function Test-InWindow([datetime]$t) {
    foreach ($w in $windows) { if ($t -ge $w.Start -and $t -le $w.End) { return $true } }
    return $false
}

# Keep only lines whose [timestamp] falls in a window; untimestamped continuation
# lines follow the decision of the previous timestamped line.
function Select-WindowLines($lines) {
    $keep = $false
    foreach ($l in $lines) {
        if ($l -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
            $keep = Test-InWindow ([datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $culture))
        }
        if ($keep) { $l }
    }
}

# --- gather candidate source files by date -------------------------------------
$byDate = @{}
if (Test-Path $serverRoot) {
    Get-ChildItem $serverRoot -Recurse -File -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.Name -match '^(\d{4}-\d{2}-\d{2})\.') {
            $d = $Matches[1]
            $day0 = [datetime]::ParseExact($d, 'yyyy-MM-dd', $culture)
            $hit = $windows | Where-Object { $_.Start -lt $day0.AddDays(1) -and $_.End -ge $day0 }
            if ($hit) {
                if (-not $byDate.ContainsKey($d)) { $byDate[$d] = @() }
                $byDate[$d] += $_
            }
        }
    }
}
$legacyLines = @()
if (Test-Path $legacyLog) {
    $legacyLines = @(Select-WindowLines (Get-Content $legacyLog -Encoding UTF8 -ErrorAction SilentlyContinue))
}

if ($byDate.Count -eq 0 -and $legacyLines.Count -eq 0) { exit 0 }
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }

foreach ($date in ($byDate.Keys | Sort-Object)) {
    $outputFile = Join-Path $outputDir "${date}_lmstudio.md"
    $files = @($byDate[$date] | Sort-Object Name)

    if ($date -ne $today -and (Test-Path $outputFile)) {
        $newest = ($files | Measure-Object LastWriteTime -Maximum).Maximum
        if ((Get-Item $outputFile).LastWriteTime -ge $newest) { continue }
    }

    $sections = @()
    foreach ($f in $files) {
        $sel = @(Select-WindowLines (Get-Content $f.FullName -Encoding UTF8 -ErrorAction SilentlyContinue))
        if ($sel.Count -gt 0) { $sections += [pscustomobject]@{ Name = $f.Name; Path = $f.FullName; Lines = $sel } }
    }
    if ($date -eq $today -and $legacyLines.Count -gt 0) {
        $sections += [pscustomobject]@{ Name = 'main.log'; Path = $legacyLog; Lines = $legacyLines }
    }
    if ($sections.Count -eq 0) { continue }

    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add("# LM Studio Log (project runs only) - $date")
    $md.Add("")
    $md.Add("- **Exported**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $md.Add("- **Filter**: only lines written while this project (Chainlit) was running")
    foreach ($s in $sections) { $md.Add("- **Source**: ``$($s.Path)`` ($($s.Lines.Count) lines)") }
    $md.Add("")
    $md.Add("---")
    foreach ($s in $sections) {
        $md.Add("")
        $md.Add("## $($s.Name)")
        $md.Add("")
        $md.Add('```')
        foreach ($line in $s.Lines) { $md.Add($line) }
        $md.Add('```')
    }
    $md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
}
