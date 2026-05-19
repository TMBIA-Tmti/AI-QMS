<#
.SYNOPSIS
  Snapshots today's entries from the Ollama server log into logs/sessions/ollama/.
  Skips gracefully if Ollama is not installed or has no activity today.
  Called by snapshot_service_logs.ps1 on session end.
#>

$projectDir = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$outputDir  = "$projectDir\logs\sessions\ollama"
$sourceLog  = "$env:LOCALAPPDATA\Ollama\server.log"
$today      = Get-Date -Format "yyyy-MM-dd"

if (-not (Test-Path $sourceLog)) { exit 0 }

$lines = Get-Content $sourceLog -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not $lines) { exit 0 }

# Filter to today's entries only (format: time=2026-05-19T...)
$todayLines = $lines | Where-Object { $_ -match "time=${today}T" -or $_ -match "\[GIN\] ${today}" }
if (-not $todayLines) { exit 0 }

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$outputFile = "$outputDir\${today}_ollama.md"

$md = [System.Collections.Generic.List[string]]::new()
$md.Add("# Ollama Server Log - $today")
$md.Add("")
$md.Add("- **Source**: ``$sourceLog``")
$md.Add("- **Exported**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$md.Add("- **Entries**: $($todayLines.Count)")
$md.Add("")
$md.Add("---")
$md.Add("")
$md.Add('```')
foreach ($line in $todayLines) { $md.Add($line) }
$md.Add('```')

$md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
