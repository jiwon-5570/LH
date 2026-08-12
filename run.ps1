[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Resolve-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Command = 'py'; Prefix = @('-3') }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Command = 'python'; Prefix = @() }
    }
    throw 'Python 3 is not installed. Install Python and try again.'
}

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host '[1/4] Creating the Python virtual environment...'
    $launcher = Resolve-PythonLauncher
    & $launcher.Command @($launcher.Prefix) -m venv .venv
}

Write-Host '[2/4] Checking required packages...'
$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $venvPython -c 'import fastapi, uvicorn, streamlit, dotenv, anthropic' 2>$null
$packagesReady = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $previousErrorActionPreference
if (-not $packagesReady) {
    Write-Host '      Installing packages. The first run may take a few minutes.'
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
}

$env:FRONTEND_API_URL = 'http://127.0.0.1:8000'
$backend = $null

try {
    if (Test-Path (Join-Path $projectRoot 'data\processed\lh_complexes')) {
        Write-Host '      Refreshing Seoul resilience profiles from validated local data...'
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $venvPython -m scripts.build_terrain_features
        & $venvPython -m scripts.build_seoul_resilience
        $profileReady = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $previousErrorActionPreference
        if (-not $profileReady) {
            Write-Warning 'Seoul profile refresh failed. The backend will start with the last committed database snapshot.'
        }
    }
    Write-Host '[3/4] Starting the LH-PREDICT backend...'
    $backend = Start-Process -FilePath $venvPython `
        -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($backend.HasExited) { throw 'The backend exited during startup.' }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { throw 'Timed out while waiting for the backend.' }

    $quality = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/data-quality' -TimeoutSec 5
    if (($quality.complex_count -as [int]) -eq 0) {
        Write-Host '      No complex data found. Importing LH complex data from the configured API...'
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $venvPython -m backend.app.collectors.cli ingest lh_complexes --max-pages 10
        $ingestSucceeded = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $previousErrorActionPreference
        if (-not $ingestSucceeded) {
            Write-Warning 'Initial LH complex import failed. The dashboard will still start; check the collector output above.'
        }
    }

    Write-Host '[4/4] Starting the dashboard: http://127.0.0.1:8501'
    Write-Host '      Press Ctrl+C to stop.'
    & $venvPython -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
} finally {
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
