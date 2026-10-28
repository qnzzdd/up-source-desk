$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$frontend = Join-Path $root 'frontend'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment missing. Follow the setup commands in README.md.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules'))) {
    throw 'Frontend dependencies missing. Run npm --prefix frontend install.'
}

Push-Location $frontend
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
finally {
    Pop-Location
}

Write-Host 'UP Source Desk demo: http://127.0.0.1:8766'
& $python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8766
