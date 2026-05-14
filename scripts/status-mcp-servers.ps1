# status-mcp-servers.ps1
# Shows health status of all MCP servers.

Set-StrictMode -Version Latest

# Bypass system proxy for localhost requests (PS 5.1 routes localhost through WinHTTP proxy).
# Must be set BEFORE $ErrorActionPreference = SilentlyContinue to avoid silent failure.
[System.Net.WebRequest]::DefaultWebProxy = [System.Net.GlobalProxySelection]::GetEmptyWebProxy()

$ErrorActionPreference = "SilentlyContinue"

$Endpoints = [ordered]@{
    "job-board"         = "http://localhost:3001/livez"
    "course-catalogue"  = "http://localhost:3002/livez"
    "salary-benchmark"  = "http://localhost:3003/livez"
    "github-trends"     = "http://localhost:3004/livez"
    "social-signals"    = "http://localhost:3005/livez"
    "calendar"          = "http://localhost:3006/livez"
    "industry-news"     = "http://localhost:3007/livez"
    "linkedin-profile"  = "http://localhost:3008/livez"
    "document-store"    = "http://localhost:3009/livez"
}

Write-Host ""
Write-Host ("  {0,-22} {1,-8} {2}" -f "Server", "Port", "Status") -ForegroundColor Cyan
Write-Host ("  " + ("-" * 50))

foreach ($name in $Endpoints.Keys) {
    $url  = $Endpoints[$name]
    $port = [regex]::Match($url, ':(\d+)/').Groups[1].Value

    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        $status = if ($r.StatusCode -eq 200) { "UP" } else { "ERR $($r.StatusCode)" }
        $color  = "Green"
    } catch {
        $status = "DOWN"
        $color  = "Red"
    }

    Write-Host ("  {0,-22} {1,-8} {2}" -f $name, $port, $status) -ForegroundColor $color
}

Write-Host ""
