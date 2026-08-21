[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$webRoot = Join-Path $projectRoot 'web'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Set-Location $projectRoot

function Resolve-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) { return @{ Command = 'py'; Prefix = @('-3') } }
    if (Get-Command python -ErrorAction SilentlyContinue) { return @{ Command = 'python'; Prefix = @() } }
    throw 'Python 3 is not installed.'
}

if (-not (Test-Path $venvPython)) {
    Write-Host '[1/4] Creating Python environment...'
    $launcher = Resolve-PythonLauncher
    & $launcher.Command @($launcher.Prefix) -m venv .venv
}

Write-Host '[2/4] Checking backend and React dependencies...'
& $venvPython -c 'import fastapi, uvicorn, dotenv, anthropic, reportlab' 2>$null
if ($LASTEXITCODE -ne 0) {
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python package installation failed.' }
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is not installed.' }
if (-not (Test-Path (Join-Path $webRoot 'node_modules'))) {
    Push-Location $webRoot
    try { & npm.cmd install } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'React package installation failed.' }
}

$backend = $null
$backendOwned = $false
try {
    $backendReady = $false
    try {
        $existingHealth = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
        $existingOpenApi = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/openapi.json' -TimeoutSec 3
        $backendReady = $existingHealth.StatusCode -eq 200 -and `
            $existingOpenApi.Content.Contains('/api/v1/seoul/reports/generate')
    } catch {}
    if ($backendReady) {
        Write-Host '[3/4] Reusing FastAPI: http://127.0.0.1:8000'
    } else {
        $staleBackend = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($staleBackend) {
            Write-Host '[3/4] Replacing stale FastAPI process...'
            Stop-Process -Id $staleBackend.OwningProcess -Force -ErrorAction Stop
        }
        Write-Host '[3/4] Starting FastAPI: http://127.0.0.1:8000'
        $backend = Start-Process -FilePath $venvPython `
            -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') `
            -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
        $backendOwned = $true
    }

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($backendOwned -and $backend.HasExited) { throw 'FastAPI exited during startup.' }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 400 }
    }
    if (-not $ready) { throw 'FastAPI startup timed out.' }

    Write-Host '[4/4] Starting React dashboard: http://127.0.0.1:8501'
    Write-Host '      Press Ctrl+C to stop both services.'
    $legacyStreamlit = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($legacyStreamlit) {
        Stop-Process -Id $legacyStreamlit.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Process 'http://127.0.0.1:8501/'
    Push-Location $webRoot
    try { & npm.cmd run dev } finally { Pop-Location }
} finally {
    if ($backendOwned -and $backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
