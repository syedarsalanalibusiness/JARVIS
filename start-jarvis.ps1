$ErrorActionPreference = 'Continue'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logPath = Join-Path $projectRoot 'outputs\startup.log'
$healthUrl = 'http://127.0.0.1:8000/health'
$restartDelaySeconds = 5

New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null

function Write-StartupLog([string]$Message) {
    "[$(Get-Date -Format o)] $Message" | Add-Content -LiteralPath $logPath
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-StartupLog 'Startup failed: project virtualenv Python was not found.'
    exit 1
}

Set-Location -LiteralPath $projectRoot
while ($true) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2 -UseBasicParsing
        if ($response.StatusCode -eq 200 -and $response.Content -match '"name"\s*:\s*"JARVIS"') {
            Write-StartupLog 'JARVIS is already healthy; startup check finished.'
            exit 0
        }
    } catch {
        # No healthy JARVIS server is responding; try to start it.
    }

    Write-StartupLog 'Starting JARVIS backend.'
    & $python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 *>> $logPath
    $exitCode = $LASTEXITCODE
    Write-StartupLog "JARVIS backend exited with code $exitCode. Retrying in $restartDelaySeconds seconds."
    Start-Sleep -Seconds $restartDelaySeconds
}
