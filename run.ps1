$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$Port = 8517
$Busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue

if ($Busy) {
    $PidOwner = $Busy[0].OwningProcess
    $Proc = Get-Process -Id $PidOwner -ErrorAction SilentlyContinue
    throw "Порт $Port уже занят процессом PID=$PidOwner $($Proc.ProcessName). Освободи порт или поменяй порт в run.ps1 и .streamlit\config.toml"
}

if (!(Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "Виртуальное окружение не найдено. Запускаю install.ps1..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File ".\install.ps1"
}

.\.venv\Scripts\Activate.ps1

Write-Host "Sovereign Cut 2.0 запускается на http://localhost:$Port" -ForegroundColor Cyan
streamlit run app.py --server.port $Port --server.address localhost
