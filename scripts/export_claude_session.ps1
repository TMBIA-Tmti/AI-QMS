<#
.SYNOPSIS
  Exports the current Claude Code session JSONL to a markdown file.
  Triggered automatically by the Claude Code Stop hook after each turn.
  Output: logs/sessions/claude/<session_id>.md  (overwritten each turn)
#>

param()

$projectKey = "C--Users-MDR-Desktop-Github-upload-AI-QMS-Phase1-DocControl"
$projectDir = "C:\Users\MDR\Desktop\Github upload\AI-QMS-Phase1-DocControl"
$outputDir  = "$projectDir\logs\sessions\claude"

# --- Read session_id from stdin (Claude Code hook protocol) ---
$sessionId = $null
try {
    $stdin = [System.Console]::In.ReadToEnd().Trim()
    if ($stdin) {
        $hookData  = $stdin | ConvertFrom-Json
        $sessionId = if ($hookData.session_id) { $hookData.session_id } else { $hookData.sessionId }
    }
} catch { }

# --- Fallback: most recently modified JSONL in the last 60 min ---
if (-not $sessionId) {
    $jsonlDir   = "$env:USERPROFILE\.claude\projects\$projectKey"
    $cutoff     = (Get-Date).AddMinutes(-60)
    $latest     = Get-ChildItem -Path $jsonlDir -Filter "*.jsonl" -File -ErrorAction SilentlyContinue |
                  Where-Object { $_.Name -match '^[0-9a-f-]{36}\.jsonl$' -and $_.LastWriteTime -gt $cutoff } |
                  Sort-Object LastWriteTime -Descending |
                  Select-Object -First 1
    if ($latest) { $sessionId = $latest.BaseName }
}

if (-not $sessionId) { exit 0 }

$jsonlPath = "$env:USERPROFILE\.claude\projects\$projectKey\$sessionId.jsonl"
if (-not (Test-Path $jsonlPath)) { exit 0 }

if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

$lines = Get-Content $jsonlPath -Encoding UTF8 -ErrorAction SilentlyContinue
if (-not $lines) { exit 0 }

# --- Find session start timestamp ---
$sessionStart = $null
foreach ($line in $lines) {
    try {
        $e = $line | ConvertFrom-Json
        if ($e.type -eq "user" -and $e.timestamp) {
            $sessionStart = [DateTime]::Parse($e.timestamp).ToLocalTime()
            break
        }
    } catch { }
}
$startStr = if ($sessionStart) { $sessionStart.ToString("yyyy-MM-dd HH:mm") } else { "Unknown" }

# --- Build markdown ---
$md = [System.Collections.Generic.List[string]]::new()
$md.Add("# Claude Session Log")
$md.Add("")
$md.Add("| Field      | Value |")
$md.Add("|------------|-------|")
$md.Add("| Session ID | ``$sessionId`` |")
$md.Add("| Started    | $startStr |")
$md.Add("| Updated    | $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') |")
$md.Add("")
$md.Add("---")
$md.Add("")

foreach ($line in $lines) {
    if (-not $line.Trim()) { continue }
    try {
        $e = $line | ConvertFrom-Json

        if ($e.type -eq "user" -and $e.message -and $null -ne $e.message.content) {
            $content = $e.message.content
            $text    = $null

            if ($content -is [string]) {
                $text = $content.Trim()
            } else {
                $parts = @($content) | Where-Object { $_ -and $_.type -eq "text" } | ForEach-Object { $_.text }
                $text  = ($parts -join "`n").Trim()
            }

            if ($text) {
                $ts = if ($e.timestamp) { [DateTime]::Parse($e.timestamp).ToLocalTime().ToString("HH:mm:ss") } else { "" }
                $md.Add("## User [$ts]")
                $md.Add("")
                $md.Add($text)
                $md.Add("")
            }
        }
        elseif ($e.type -eq "assistant" -and $e.message -and $null -ne $e.message.content) {
            $content = $e.message.content
            $parts   = @()

            if ($content -is [string]) {
                $parts = @($content.Trim())
            } else {
                $parts = @($content) | Where-Object { $_ -and $_.type -eq "text" } | ForEach-Object { $_.text.Trim() }
            }

            $text = ($parts -join "`n").Trim()
            if ($text) {
                $ts = if ($e.timestamp) { [DateTime]::Parse($e.timestamp).ToLocalTime().ToString("HH:mm:ss") } else { "" }
                $md.Add("## Claude [$ts]")
                $md.Add("")
                $md.Add($text)
                $md.Add("")
            }
        }
    } catch { }
}

$outputFile = "$outputDir\$sessionId.md"
$md | Out-File -FilePath $outputFile -Encoding UTF8 -Force
