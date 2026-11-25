# Builds the web interface (first run only) and starts NGSentinel at http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path "frontend/dist/index.html")) {
    Push-Location frontend
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build
    Pop-Location
}
Write-Host "NGSentinel running at http://127.0.0.1:8000  (Ctrl+C to stop)"
python -m uvicorn ngsentinel.api:app --app-dir backend --host 127.0.0.1 --port 8000
