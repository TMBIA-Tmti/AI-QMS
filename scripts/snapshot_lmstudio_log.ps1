<#
.SYNOPSIS
  Snapshots today's entries from the LM Studio server log into logs/sessions/lmstudio/.
  Skips gracefully if LM Studio is not installed or has no activity today.
  Called by snapshot_service_logs.ps1 on session end.
#>

$projectDir = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$outputDir  = "$projectDir\logs\sessions\lmstudio"
$sourceLog  = "$env:APPDATA\LM Studio\logs\main.log"
$today      = Get-Date -Format "yyyy-MM-dd"

if (-not (Test-Path $sourceLog)) { exit 0 }

$lines = Get-Content $sourceLog -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not $lines) { exit 0 }

# Filter to today's entries only (format: [2026-05-19 HH:mm:ss.mmm])
$todayLines = $lines | Where-Object { $_ -match "\[$today" }
if (-not $todayLines) { exit 0 }

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$outputFile = "$outputDir\${today}_lmstudio.md"

$md = [System.Collections.Generic.List[string]]::new()
$md.Add("# LM Studio Server Log - $today")
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
