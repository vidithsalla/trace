# Trace control script for Windows: start | stop | status | logs | demo | uninstall
param([Parameter(Position = 0)][string]$Command = "")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Get-EnvValue([string]$key) {
  $line = Get-Content .env -ErrorAction SilentlyContinue | Where-Object { $_ -match "^$key=" } | Select-Object -Last 1
  if ($line) { $line.Split("=", 2)[1] } else { "" }
}
function Invoke-Compose([string[]]$rest) {
  $files = @("compose", "--env-file", ".env", "-f", "infra/compose/compose.yaml")
  if ((Get-EnvValue "TRACE_MODEL_PROVIDER") -eq "local") { $files += @("-f", "infra/compose/compose.model.yaml") }
  & docker @files @rest
  if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
}

switch ($Command) {
  "start" {
    if (-not (Test-Path .env)) { Write-Host "No .env found. Run .\install.ps1 first." -ForegroundColor Red; exit 1 }
    Write-Host "Starting Trace (first start builds images; this can take a few minutes) ..."
    Invoke-Compose @("up", "-d", "--build")
    $port = Get-EnvValue "TRACE_WEB_PORT"; if (-not $port) { $port = "3000" }
    for ($i = 0; $i -lt 90; $i++) {
      try { Invoke-WebRequest -Uri "http://127.0.0.1:$port/sign-in" -UseBasicParsing -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
    }
    Write-Host "Trace is running: http://127.0.0.1:$port  (attorney@trace.local / trace-demo-password)"
  }
  "stop" { Invoke-Compose @("stop"); Write-Host "Trace stopped. Your data is kept." }
  "status" { Invoke-Compose @("ps") }
  "logs" { Invoke-Compose @("logs", "--tail=200", "-f") }
  "demo" {
    Invoke-Compose @("exec", "-T", "api", "uv", "run", "python", "-m", "app.scripts.seed_demo", "--mode", "fast")
    Invoke-Compose @("exec", "-T", "api", "uv", "run", "python", "-m", "app.scripts.seed_v3_demo")
  }
  "uninstall" {
    $answer = Read-Host "This deletes Trace's containers AND data volumes. Type 'delete' to confirm"
    if ($answer -ne "delete") { Write-Host "Cancelled."; exit 1 }
    Invoke-Compose @("down", "--volumes", "--remove-orphans")
  }
  default { Write-Host "Usage: .\trace.ps1 {start|stop|status|logs|demo|uninstall}"; exit 1 }
}
