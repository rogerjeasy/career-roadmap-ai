# stop-mcp-servers.ps1
# Stops all MCP servers started by start-mcp-servers.ps1.
# Reads PIDs from logs/mcp/mcp-pids.json, also kills by port as a fallback.

param(
    [string[]]$Servers = @()   # empty = stop all
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

$RepoRoot = $PSScriptRoot | Split-Path -Parent
$PidFile  = Join-Path $RepoRoot "logs\mcp\mcp-pids.json"

$Ports = [ordered]@{
    "job-board"         = 3001
    "course-catalogue"  = 3002
    "salary-benchmark"  = 3003
    "github-trends"     = 3004
    "social-signals"    = 3005
    "calendar"          = 3006
    "industry-news"     = 3007
    "linkedin-profile"  = 3008
    "document-store"    = 3009
}

$targets = if ($Servers.Count -gt 0) { $Servers } else { @($Ports.Keys) }

Write-Host ""
Write-Host "Stopping MCP servers..." -ForegroundColor Cyan
Write-Host ("-" * 50)

# Try PID file first
$PidMap = @{}
if (Test-Path $PidFile) {
    $json = Get-Content $PidFile | ConvertFrom-Json
    $json.PSObject.Properties | ForEach-Object { $PidMap[$_.Name] = [int]$_.Value }
}

foreach ($name in $targets) {
    $stopped = $false

    # Kill by saved PID — use /T to kill the entire process tree (reloader + all workers)
    if ($PidMap.ContainsKey($name)) {
        $savedPid = $PidMap[$name]
        $proc = Get-Process -Id $savedPid -ErrorAction SilentlyContinue
        if ($proc) {
            & taskkill /PID $savedPid /T /F 2>&1 | Out-Null
            Write-Host ("  {0,-22} stopped (PID {1} + tree)" -f $name, $savedPid) -ForegroundColor Green
            $stopped = $true
        }
    }

    # Fallback: kill by port — also walk up to kill the reloader parent
    if (-not $stopped -and $Ports.Contains($name)) {
        $port = $Ports[$name]
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) {
            $childPid = $conn.OwningProcess
            # Walk up to the reloader parent so we kill the whole tree
            $wmi = Get-WmiObject -Query "SELECT ParentProcessId FROM Win32_Process WHERE ProcessId = $childPid" -ErrorAction SilentlyContinue
            $rootPid = if ($wmi -and $wmi.ParentProcessId -gt 4) { $wmi.ParentProcessId } else { $childPid }
            & taskkill /PID $rootPid /T /F 2>&1 | Out-Null
            & taskkill /PID $childPid /T /F 2>&1 | Out-Null
            Write-Host ("  {0,-22} stopped via port {1} (PIDs {2},{3}+tree)" -f $name, $port, $rootPid, $childPid) -ForegroundColor Green
            $stopped = $true
        }
    }

    if (-not $stopped) {
        Write-Host ("  {0,-22} not running" -f $name) -ForegroundColor DarkGray
    }
}

# Remove PID file
if ($Servers.Count -eq 0) {
    Remove-Item $PidFile -ErrorAction SilentlyContinue
} else {
    # Remove only the stopped entries
    foreach ($name in $targets) { $PidMap.Remove($name) }
    if ($PidMap.Count -gt 0) { $PidMap | ConvertTo-Json | Set-Content $PidFile }
    else { Remove-Item $PidFile -ErrorAction SilentlyContinue }
}

Write-Host ("-" * 50)
Write-Host ""
