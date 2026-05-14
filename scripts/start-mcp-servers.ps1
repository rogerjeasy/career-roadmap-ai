# start-mcp-servers.ps1
# Starts all 9 career-roadmap MCP servers using the shared apps/api/.venv.
# Each server runs as a background Process with stdout/stderr piped to logs/mcp/<name>.log.
#
# Usage:
#   .\scripts\start-mcp-servers.ps1                  # start all servers
#   .\scripts\start-mcp-servers.ps1 -Servers salary-benchmark,github-trends
#   .\scripts\start-mcp-servers.ps1 -WaitForHealth    # block until all pass /livez
#
# Stop:   .\scripts\stop-mcp-servers.ps1   or   make mcp-stop
# Status: .\scripts\status-mcp-servers.ps1  or   make mcp-status

param(
    [string[]]$Servers = @(
        "job-board",
        "course-catalogue",
        "salary-benchmark",
        "github-trends",
        "social-signals",
        "calendar",
        "industry-news",
        "linkedin-profile",
        "document-store"
    ),
    [switch]$WaitForHealth
)

Set-StrictMode -Version Latest

# Bypass system proxy for localhost health checks (PS 5.1 routes localhost through WinHTTP proxy).
# Must be set before $ErrorActionPreference changes that could mask silent failure.
[System.Net.WebRequest]::DefaultWebProxy = [System.Net.GlobalProxySelection]::GetEmptyWebProxy()

$ErrorActionPreference = "Stop"

# --- Resolve paths ---
$RepoRoot = $PSScriptRoot | Split-Path -Parent
$McpRoot  = Join-Path $RepoRoot "mcp-servers"
$VenvUvi  = Join-Path $RepoRoot "apps\api\.venv\Scripts\uvicorn.exe"
$LogDir   = Join-Path $RepoRoot "logs\mcp"

if (-not (Test-Path $VenvUvi)) {
    Write-Error "uvicorn not found at $VenvUvi -- run 'make install-api' first."
    exit 1
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# --- Server registry (name -> port) ---
$Registry = [ordered]@{
    "job-board"        = 3001
    "course-catalogue" = 3002
    "salary-benchmark" = 3003
    "github-trends"    = 3004
    "social-signals"   = 3005
    "calendar"         = 3006
    "industry-news"    = 3007
    "linkedin-profile" = 3008
    "document-store"   = 3009
}

# --- PID tracking ---
$PidFile = Join-Path $LogDir "mcp-pids.json"
$PidMap  = @{}

if (Test-Path $PidFile) {
    $old = Get-Content $PidFile | ConvertFrom-Json
    $old.PSObject.Properties | ForEach-Object { $PidMap[$_.Name] = $_.Value }
}

# --- Launch ---
Write-Host ""
Write-Host "Starting MCP servers..." -ForegroundColor Cyan
Write-Host ("-" * 60)

foreach ($name in $Servers) {
    if (-not $Registry.Contains($name)) {
        Write-Warning "Unknown server '$name' -- skipping."
        continue
    }

    $port    = $Registry[$name]
    $srvDir  = Join-Path $McpRoot $name
    $logFile = Join-Path $LogDir "$name.log"

    # Kill any existing process on this port — use taskkill /T /F to kill the
    # entire uvicorn process tree (reloader parent + worker child). Stop-Process
    # only kills the child; the reloader parent survives and immediately respawns
    # a new child from cached .pyc files, ignoring any code changes on disk.
    $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        $childPid = $existing.OwningProcess
        $wmi = Get-WmiObject -Query "SELECT ParentProcessId FROM Win32_Process WHERE ProcessId = $childPid" -ErrorAction SilentlyContinue
        $rootPid = if ($wmi -and $wmi.ParentProcessId -gt 4) { $wmi.ParentProcessId } else { $childPid }
        Write-Host ("  Stopping old process tree on port {0} (PIDs {1},{2})..." -f $port, $rootPid, $childPid) -ForegroundColor Yellow
        & taskkill /PID $rootPid /T /F 2>&1 | Out-Null
        & taskkill /PID $childPid /T /F 2>&1 | Out-Null
        Start-Sleep -Milliseconds 800   # wait for OS to release the port
    }

    # PYTHONPATH: shared mcp-servers root + this server's own directory
    $pyPath = $McpRoot + ";" + $srvDir

    $uvArgs = @(
        "server:app",
        "--host", "0.0.0.0",
        "--port", "$port",
        "--reload"
    )

    $procArgs = @{
        FilePath               = $VenvUvi
        ArgumentList           = $uvArgs
        WorkingDirectory       = $srvDir
        RedirectStandardOutput = $logFile
        RedirectStandardError  = ($logFile + ".err")
        WindowStyle            = "Hidden"
        PassThru               = $true
    }

    # Set PYTHONPATH before spawning so the child process inherits it.
    # Restore immediately after -- Start-Process is synchronous up to process creation.
    $env:PYTHONPATH = $pyPath
    $newProc = Start-Process @procArgs
    $env:PYTHONPATH = ""
    $PidMap[$name] = $newProc.Id
    Write-Host ("  {0,-22} port {1}   PID {2,-7}  log: logs/mcp/{0}.log" -f $name, $port, $newProc.Id) -ForegroundColor Green
}

# Persist PIDs so stop-mcp-servers.ps1 can find them
$PidMap | ConvertTo-Json | Set-Content $PidFile

Write-Host ("-" * 60)

# --- Optional health check ---
if ($WaitForHealth) {
    Write-Host ""
    Write-Host "Waiting for /livez on all servers (30s timeout)..." -ForegroundColor Cyan

    $healthUrls = [ordered]@{
        "job-board"        = "http://localhost:3001/livez"
        "course-catalogue" = "http://localhost:3002/livez"
        "salary-benchmark" = "http://localhost:3003/livez"
        "github-trends"    = "http://localhost:3004/livez"
        "social-signals"   = "http://localhost:3005/livez"
        "calendar"         = "http://localhost:3006/livez"
        "industry-news"    = "http://localhost:3007/livez"
        "linkedin-profile" = "http://localhost:3008/livez"
        "document-store"   = "http://localhost:3009/livez"
    }

    $remaining = [System.Collections.Generic.HashSet[string]]::new($Servers)
    $deadline  = (Get-Date).AddSeconds(30)

    while ($remaining.Count -gt 0 -and (Get-Date) -lt $deadline) {
        foreach ($name in @($remaining)) {
            if (-not $healthUrls.Contains($name)) {
                $remaining.Remove($name) | Out-Null
                continue
            }
            try {
                $r = Invoke-WebRequest -Uri $healthUrls[$name] -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
                if ($r.StatusCode -eq 200) {
                    Write-Host ("  {0,-22} UP" -f $name) -ForegroundColor Green
                    $remaining.Remove($name) | Out-Null
                }
            } catch { }
        }
        if ($remaining.Count -gt 0) { Start-Sleep -Milliseconds 500 }
    }

    if ($remaining.Count -gt 0) {
        Write-Warning ("Timed out waiting for: {0}.  Check logs/mcp/<name>.log" -f ($remaining -join ", "))
    }
}

Write-Host ""
Write-Host "Add these to apps/api/.env to activate live data:" -ForegroundColor Yellow
Write-Host "  MCP_JOB_BOARD_URL=http://localhost:3001"
Write-Host "  MCP_COURSE_CATALOG_URL=http://localhost:3002"
Write-Host "  MCP_SALARY_BENCHMARK_URL=http://localhost:3003"
Write-Host "  MCP_GITHUB_TRENDS_URL=http://localhost:3004"
Write-Host "  MCP_SOCIAL_SIGNALS_URL=http://localhost:3005"
Write-Host "  MCP_CALENDAR_URL=http://localhost:3006"
Write-Host "  MCP_INDUSTRY_NEWS_URL=http://localhost:3007"
Write-Host "  MCP_LINKEDIN_PROFILE_URL=http://localhost:3008"
Write-Host "  MCP_DOCUMENT_STORE_URL=http://localhost:3009"
Write-Host ""
Write-Host "Stop all:  .\scripts\stop-mcp-servers.ps1" -ForegroundColor DarkGray
Write-Host "Status:    .\scripts\status-mcp-servers.ps1" -ForegroundColor DarkGray
Write-Host ""
