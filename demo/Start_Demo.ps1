$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ollama = Join-Path $workspace 'work\ollama\bin\ollama.exe'
$models = Join-Path $workspace 'work\ollama\models'
$python = 'C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1119-907-0_26.1119.907.0_x64__3k8sg7r9htsxt\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $ollama)) { throw 'Local Ollama binary is missing from work\ollama\bin.' }
if (-not (Test-Path -LiteralPath $python)) { throw 'Bundled Python runtime is missing.' }
$env:OLLAMA_MODELS = $models
$env:RAKURAKU_LLM_URL = 'http://127.0.0.1:11434/v1/chat/completions'
$env:RAKURAKU_LLM_MODEL = 'qwen3:4b-instruct'
try { Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null }
catch { Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden; Start-Sleep -Seconds 2 }
Write-Host 'Open http://127.0.0.1:8765 after the server starts. Press Ctrl+C to stop.'
& $python (Join-Path $PSScriptRoot 'rakuraku_app.py')
