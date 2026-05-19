<#
.SYNOPSIS
  Wrapper: runs all service log snapshots (Ollama, LM Studio, Phoenix) at session end.
  Called automatically by convert_terminal_log.ps1 on PowerShell exit.
  Can also be run manually at any time.
#>

$projectDir = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$scripts    = @(
    "$projectDir\scripts\snapshot_ollama_log.ps1",
    "$projectDir\scripts\snapshot_lmstudio_log.ps1",
    "$projectDir\scripts\export_phoenix_traces.ps1"
)

foreach ($script in $scripts) {
    if (Test-Path $script) {
        try {
            & $script
        } catch { }
    }
}
