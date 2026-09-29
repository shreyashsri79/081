# Start the Samanvay dashboard on real data: API (port 8081) + web (port 5181), then open the browser.
# Usage, from the repo folder:  .\start.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -c "import fastapi, uvicorn, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing server requirements..."
    python -m pip install -q -r requirements-server.txt
}
if (-not (Test-Path "web\node_modules")) {
    Write-Host "Installing web dependencies..."
    Push-Location web; npm install --no-audit --no-fund; Pop-Location
}

$env:BLEND_BUNDLES = Join-Path $root "bundles"
$api = Start-Process python -ArgumentList "-m", "uvicorn", "blend.server:app", "--host", "127.0.0.1", "--port", "8081" `
    -WorkingDirectory $root -PassThru -WindowStyle Minimized
$web = Start-Process "cmd.exe" -ArgumentList "/c", "npm run dev -- --host 127.0.0.1" `
    -WorkingDirectory (Join-Path $root "web") -PassThru -WindowStyle Minimized

Write-Host "Waiting for the API and the dashboard..."
foreach ($i in 1..60) {
    try {
        $h = Invoke-RestMethod "http://127.0.0.1:5181/api/health" -TimeoutSec 2
        if ($h.status -eq "ok") { break }
    } catch { Start-Sleep -Seconds 1 }
}
Write-Host "API: $($h.runs) runs, provenance $($h.provenance)"
Start-Process "http://127.0.0.1:5181"
Write-Host "Dashboard: http://127.0.0.1:5181   (stop: close the two minimized windows, or"
Write-Host "  Stop-Process -Id $($api.Id), $($web.Id))"
