<#
.SYNOPSIS
  Exports new Arize Phoenix traces into logs/phoenix/export/.
  Thin wrapper around scripts/export_phoenix_traces.py, which reads phoenix.db
  directly (no running server / fixed port required). Called by
  snapshot_service_logs.ps1 on session end; also run automatically by the
  start*.bat launchers.
#>
$projectDir = Split-Path -Parent $PSScriptRoot
$script     = Join-Path $PSScriptRoot "export_phoenix_traces.py"
$python     = (Get-Command python -ErrorAction SilentlyContinue).Source
$qms        = Join-Path $env:USERPROFILE "miniconda3\envs\QMS\python.exe"
if (Test-Path $qms) { $python = $qms }
if ($python -and (Test-Path $script)) { & $python $script }
exit 0
