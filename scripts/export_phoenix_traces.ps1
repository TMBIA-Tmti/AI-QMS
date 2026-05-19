<#
.SYNOPSIS
  Exports today's LLM traces from Arize Phoenix into logs/sessions/phoenix/.
  Tries Phoenix REST API first; skips gracefully if Phoenix is not running.
  Called by snapshot_service_logs.ps1 on session end.
#>

$projectDir  = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$outputDir   = "$projectDir\logs\sessions\phoenix"
$today       = Get-Date -Format "yyyy-MM-dd"
$outputFile  = "$outputDir\${today}_phoenix.md"
$phoenixBase = "http://localhost:6006"

# --- Check if Phoenix is reachable ---
$running = $false
try {
    $null = Invoke-WebRequest -Uri "$phoenixBase" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $running = $true
} catch { }

if (-not $running) { exit 0 }

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

# --- Try to get project list ---
$projects = @()
try {
    $resp = Invoke-RestMethod -Uri "$phoenixBase/v1/projects" -TimeoutSec 5 -ErrorAction Stop
    if ($resp.data) { $projects = $resp.data | ForEach-Object { $_.name } }
} catch { }

if (-not $projects) { $projects = @("ai-qms-main", "ai-qms-doc-control") }

# --- Build markdown ---
$md = [System.Collections.Generic.List[string]]::new()
$md.Add("# Phoenix LLM Traces - $today")
$md.Add("")
$md.Add("- **Endpoint**: ``$phoenixBase``")
$md.Add("- **Exported**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
$md.Add("")
$md.Add("---")
$md.Add("")

$totalSpans = 0

foreach ($project in $projects) {
    $spans = @()
    try {
        $resp = Invoke-RestMethod -Uri "$phoenixBase/v1/spans?project_name=$project" -TimeoutSec 10 -ErrorAction Stop
        if ($resp.data) { $spans = $resp.data }
    } catch { }

    # Filter to today's spans
    $todaySpans = $spans | Where-Object {
        $_.start_time -and $_.start_time.StartsWith($today)
    }

    if (-not $todaySpans) { continue }

    $totalSpans += $todaySpans.Count
    $md.Add("## Project: $project ($($todaySpans.Count) spans)")
    $md.Add("")
    $md.Add("| Time | Name | Model | Status | Latency(s) | Tokens |")
    $md.Add("|------|------|-------|--------|------------|--------|")

    foreach ($span in ($todaySpans | Sort-Object start_time)) {
        $time    = if ($span.start_time) { $span.start_time.Substring(11,8) } else { "-" }
        $name    = if ($span.name)       { $span.name }                        else { "-" }
        $attrs   = $span.attributes
        $modelProp = if ($attrs) { $attrs.PSObject.Properties["llm.model_name"] } else { $null }
        $model   = if ($modelProp) { $modelProp.Value } else { "-" }
        $status  = if ($span.status_code) { $span.status_code } else { "-" }
        $latency = if ($span.latency_ms)  { [math]::Round($span.latency_ms / 1000, 2) } else { "-" }
        $tokenProp = if ($attrs) { $attrs.PSObject.Properties["llm.token_count.total"] } else { $null }
        $tokens  = if ($tokenProp) { $tokenProp.Value } else { "-" }
        $md.Add("| $time | $name | $model | $status | $latency | $tokens |")
    }
    $md.Add("")
}

if ($totalSpans -eq 0) { exit 0 }

$md.Insert(4, "- **Total spans today**: $totalSpans")
$md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
