<#
.SYNOPSIS
  Snapshots the Ollama server-log lines written WHILE THIS PROJECT WAS RUNNING into
  logs/sessions/ollama/<date>_ollama.md.

  A project run window = [start stamp in logs/chainlit/<stamp>_chainlit.log or
  <stamp>_console.log, that file's last write time]. Ollama activity outside these
  windows (other apps / other projects) is NOT exported.
  Skips gracefully if Ollama has no log or nothing happened during a project run.
  Called by snapshot_service_logs.ps1 on session end; safe to run manually.
#>

$projectDir = Split-Path -Parent $PSScriptRoot
$outputDir  = Join-Path $projectDir "logs\sessions\ollama"
$chainDir   = Join-Path $projectDir "logs\chainlit"
$sourceLog  = Join-Path $env:LOCALAPPDATA "Ollama\server.log"
$culture    = [Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path $sourceLog)) { exit 0 }

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

# Ollama formats: time=2026-05-19T10:12:00.123+08:00 ...   |   [GIN] 2026/05/19 - 10:12:00 | ...
# Lines without a timestamp follow the decision of the previous timestamped line.
$byDate = @{}
$keep = $false; $curDate = $null
foreach ($l in (Get-Content $sourceLog -Encoding UTF8 -ErrorAction SilentlyContinue)) {
    $t = $null
    if ($l -match 'time=(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})') {
        $t = [datetime]::ParseExact("$($Matches[1]) $($Matches[2])", 'yyyy-MM-dd HH:mm:ss', $culture)
    } elseif ($l -match '\[GIN\] (\d{4})/(\d{2})/(\d{2}) - (\d{2}:\d{2}:\d{2})') {
        $t = [datetime]::ParseExact("$($Matches[1])-$($Matches[2])-$($Matches[3]) $($Matches[4])", 'yyyy-MM-dd HH:mm:ss', $culture)
    }
    if ($t) { $keep = Test-InWindow $t; $curDate = $t.ToString('yyyy-MM-dd') }
    if ($keep -and $curDate) {
        if (-not $byDate.ContainsKey($curDate)) { $byDate[$curDate] = [System.Collections.Generic.List[string]]::new() }
        $byDate[$curDate].Add($l)
    }
}
if ($byDate.Count -eq 0) { exit 0 }
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Force -Path $outputDir | Out-Null }

foreach ($date in ($byDate.Keys | Sort-Object)) {
    $outputFile = Join-Path $outputDir "${date}_ollama.md"
    $lines = $byDate[$date]

    # Rotated logs only hold recent days: never replace an existing (older) snapshot
    # with a smaller one.
    if (Test-Path $outputFile) {
        $old = (Select-String -Path $outputFile -Pattern '\*\*Entries\*\*: (\d+)' | Select-Object -First 1)
        if ($old -and [int]$old.Matches[0].Groups[1].Value -gt $lines.Count) { continue }
    }

    $md = [System.Collections.Generic.List[string]]::new()
    $md.Add("# Ollama Server Log (project runs only) - $date")
    $md.Add("")
    $md.Add("- **Source**: ``$sourceLog``")
    $md.Add("- **Filter**: only lines written while this project (Chainlit) was running")
    $md.Add("- **Exported**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $md.Add("- **Entries**: $($lines.Count)")
    $md.Add("")
    $md.Add("---")
    $md.Add("")
    $md.Add('```')
    foreach ($line in $lines) { $md.Add($line) }
    $md.Add('```')
    $md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
}
