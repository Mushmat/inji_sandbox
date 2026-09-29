<#
Starts the Present & Verify demo on Windows in one go:
  1. an https tunnel to Inji Verify (Inji Web only posts to https without a port, FINDINGS W2),
  2. Inji Verify with that address as its response_uri base,
  3. (optional) our verifier in Inji Web's trusted list + a Mimoto restart,
  4. the demo page on http://localhost:5002.
Run again whenever the tunnel address changes (it changes every time the tunnel container restarts).

Usage (from the repo root, PowerShell):
  .\verify\tools\start-demo.ps1 -Python "D:\path\to\.venv\Scripts\python.exe" [-VerifyPort 8082] [-WalletCompose ".\wallet\docker-compose"]
Assumes Certify is already running and the mosip_network Docker network exists.
#>
param(
  [string]$Python = "python",
  [int]$VerifyPort = 8080,
  [string]$WalletCompose = "",
  [string]$ClientId = "inji-sandbox-playground"
)
# docker writes progress to stderr; in Windows PowerShell 5.1 that must not count as an error
$ErrorActionPreference = "Continue"
$verify = Split-Path -Parent $PSScriptRoot
$tunnelName = "inji-verify-tunnel"
$verifyContainer = "inji-verify-verify-service-1"

# 1. tunnel
$exists = docker ps -a --filter "name=^$tunnelName$" --format "{{.Names}}"
if (-not $exists) {
  docker run -d --name $tunnelName --restart unless-stopped --network mosip_network `
    cloudflare/cloudflared:latest tunnel --no-autoupdate --url "http://${verifyContainer}:8080" | Out-Null
} else {
  docker start $tunnelName | Out-Null
}
$url = $null
for ($i = 0; $i -lt 30 -and -not $url; $i++) {
  Start-Sleep 2
  $url = cmd /c "docker logs $tunnelName 2>&1" | Select-String -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -AllMatches |
         ForEach-Object { $_.Matches.Value } | Select-Object -Last 1
}
if (-not $url) { throw "tunnel did not report an address; check: docker logs $tunnelName" }
Write-Host "Tunnel: $url"

# 2. Inji Verify with the tunnel as its public base
Push-Location (Join-Path $verify "docker-compose")
$env:VERIFY_PORT = "$VerifyPort"; $env:VERIFY_PUBLIC_URL = $url
cmd /c "docker compose up -d 2>&1" | Select-Object -Last 2
Pop-Location

# 3. Inji Web trusted verifier (optional)
if ($WalletCompose) {
  $tv = Join-Path $WalletCompose "config\mimoto-trusted-verifiers.json"
  $j = Get-Content $tv -Raw | ConvertFrom-Json
  $entry = [pscustomobject]@{ client_id = $ClientId; redirect_uris = @();
    response_uris = @("$url/v1/verify/vp-submission/direct-post"); allow_unsigned_request = $true }
  $j.verifiers = @($j.verifiers | Where-Object { $_.client_id -ne $ClientId }) + $entry
  [IO.File]::WriteAllText((Resolve-Path $tv), ($j | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding $false))
  docker restart mimoto-service | Out-Null
  Write-Host "Updated $tv and restarted mimoto-service (sign in to Inji Web again)."
}

# 4. demo page
# stop an earlier demo page (whatever listens on 5002), leave other Python processes alone
Get-NetTCPConnection -State Listen -LocalPort 5002 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
$env:INJI_VERIFY_URL = "http://localhost:$VerifyPort/v1/verify"
$env:WALLET_URL_REWRITES = "$url=http://localhost:$VerifyPort"
$env:PYTHONIOENCODING = "utf-8"
Start-Process -WindowStyle Hidden -WorkingDirectory (Join-Path $verify "demo-ui") -FilePath $Python -ArgumentList "server.py"
Write-Host "Demo page: http://localhost:5002   (response_uri: $url/v1/verify/vp-submission/direct-post)"
