$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$Port = 8517
$VenvPython = ".\.venv\Scripts\python.exe"

$Busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($Busy) {
    $PidOwner = $Busy[0].OwningProcess
    $Proc = Get-Process -Id $PidOwner -ErrorAction SilentlyContinue
    throw "Порт $Port уже занят: PID=$PidOwner Process=$($Proc.ProcessName)"
}

if (!(Test-Path $VenvPython)) {
    Write-Host "Виртуальное окружение не найдено. Создаю..." -ForegroundColor Yellow
    python -m venv .venv
}

& $VenvPython -m pip install -r requirements.txt

if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg не найден. Поставь: winget install -e --id Gyan.FFmpeg, потом перезапусти PowerShell."
}

Write-Host "Sovereign Cut 2.1 запускается на http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Чтобы остановить сервер: Ctrl + C" -ForegroundColor Yellow

& $VenvPython -m streamlit run app.py --server.port $Port --server.address localhost
