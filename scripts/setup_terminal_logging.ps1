<#
.SYNOPSIS
  One-time setup: adds session transcript logging to the PowerShell profile.
  Run once; every new terminal session will be auto-logged afterwards.

USAGE:
  powershell -ExecutionPolicy Bypass -File setup_terminal_logging.ps1
#>

$projectDir    = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$convertScript = "$projectDir\scripts\convert_terminal_log.ps1"
$outputDir     = "$projectDir\logs\sessions\terminal"
$markerStart   = "# <<AI-QMS-session-logging-start>>"
$markerEnd     = "# <<AI-QMS-session-logging-end>>"

# Ensure output directory exists
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    Write-Host "[OK] Created: $outputDir"
}

# Ensure profile file exists
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Force -Path $PROFILE | Out-Null
    Write-Host "[OK] Created profile: $PROFILE"
}

$existing = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($existing -and $existing.Contains($markerStart)) {
    Write-Host "[SKIP] Terminal logging already configured in profile."
    Write-Host "       Profile: $PROFILE"
    exit 0
}

$snippet = @"


$markerStart
`$global:_qms_transcript = "`$env:TEMP\qms_ps_`$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
Start-Transcript -Path `$global:_qms_transcript -Append | Out-Null
Register-EngineEvent PowerShell.Exiting -Action {
    Stop-Transcript | Out-Null
    & "$convertScript" -TranscriptPath `$global:_qms_transcript
} | Out-Null
$markerEnd
"@

Add-Content -Path $PROFILE -Value $snippet -Encoding UTF8
Write-Host "[OK] Terminal logging added to profile: $PROFILE"
Write-Host "     Restart PowerShell to activate."
