# First-time setup for Trace on Windows (PowerShell 5.1+ or 7).
#
#   .\install.ps1          local model via Ollama if available (recommended)
#   .\install.ps1 -Mock    deterministic mock model, no model download
#
# Checks Docker, writes a .env with generated secrets, optionally pulls two Ollama models, builds
# and starts the containers, and loads synthetic demo data. Installs nothing system-wide.
param([switch]$Mock, [switch]$Local)
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Info($m) { Write-Host $m -ForegroundColor White }
function Warn($m) { Write-Host $m -ForegroundColor Yellow }
function Die($m) { Write-Host $m -ForegroundColor Red; exit 1 }

$LlmModel = "qwen2.5:7b-instruct"
$EmbedModel = "all-minilm:l6-v2"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Die "Docker is required. Install Docker Desktop: https://docs.docker.com/get-docker/" }
docker info *> $null; if ($LASTEXITCODE -ne 0) { Die "Docker is installed but not running. Start Docker Desktop, then rerun .\install.ps1" }

function New-RandomHex([int]$bytes) {
  $buffer = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
  -join ($buffer | ForEach-Object { $_.ToString("x2") })
}
function Set-EnvValue([string]$key, [string]$value) {
  $lines = @(Get-Content .env)
  $found = $false
  $lines = $lines | ForEach-Object { if ($_ -match "^$key=") { $found = $true; "$key=$value" } else { $_ } }
  if (-not $found) { $lines += "$key=$value" }
  Set-Content -Path .env -Value $lines -Encoding ascii
}

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Set-EnvValue "TRACE_SECRET_KEY" (New-RandomHex 32)
  Set-EnvValue "TRACE_POSTGRES_PASSWORD" (New-RandomHex 16)
  Info "Created .env with generated secrets (kept local; never committed)."
} else { Info "Using existing .env." }

function Test-Ollama { try { Invoke-RestMethod -Uri http://127.0.0.1:11434/api/version -TimeoutSec 3 | Out-Null; $true } catch { $false } }
$mode = if ($Mock) { "mock" } elseif ($Local) { "local" } elseif ((Get-Command ollama -ErrorAction SilentlyContinue) -or (Test-Ollama)) { "local" } else { "mock" }

if ($mode -eq "local") {
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Die "Ollama not found. Install it from https://ollama.com/download, or rerun with -Mock." }
  if (-not (Test-Ollama)) { Die "Ollama is installed but not running. Start the Ollama app (or 'ollama serve'), then rerun." }
  Info "Pulling local models (about 4.8 GB the first time) ..."
  ollama pull $LlmModel; ollama pull $EmbedModel
  Set-EnvValue "TRACE_MODEL_PROVIDER" "local"
  Set-EnvValue "TRACE_MODEL_NAME" $LlmModel
  Info "Using local model $LlmModel. Documents never leave this machine."
} else {
  Set-EnvValue "TRACE_MODEL_PROVIDER" "mock"
  Warn "Using the deterministic mock model (labeled as such in the UI). Install Ollama and rerun for real local inference."
}

& "$PSScriptRoot\trace.ps1" start
& "$PSScriptRoot\trace.ps1" demo
Info "Done. Open http://127.0.0.1:3000  -  Stop with .\trace.ps1 stop"
