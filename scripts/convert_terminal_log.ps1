<#
.SYNOPSIS
  Converts a PowerShell transcript file to markdown.
  Called automatically on PowerShell exit by the profile hook (setup_terminal_logging.ps1).
#>

param(
    [Parameter(Mandatory)][string]$TranscriptPath
)

$projectDir = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$outputDir  = "$projectDir\logs\sessions\terminal"

if (-not (Test-Path $TranscriptPath)) { exit 0 }

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$timestamp  = Get-Date -Format "yyyy-MM-dd_HH-mm"
$outputFile = "$outputDir\${timestamp}_terminal.md"

$raw = Get-Content $TranscriptPath -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not $raw) { exit 0 }

$md = [System.Collections.Generic.List[string]]::new()
$md.Add("# Terminal Session Log")
$md.Add("")
$md.Add("- **Date**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$md.Add("")
$md.Add("---")
$md.Add("")
$md.Add('```powershell')
foreach ($line in $raw) { $md.Add($line) }
$md.Add('```')

$md | Out-File -FilePath $outputFile -Encoding UTF8 -Force

Remove-Item $TranscriptPath -Force -ErrorAction SilentlyContinue

# Snapshot service logs (Ollama, LM Studio, Phoenix) at the same session boundary
$serviceScript = "$projectDir\scripts\snapshot_service_logs.ps1"
if (Test-Path $serviceScript) {
    try { & $serviceScript } catch { }
}
