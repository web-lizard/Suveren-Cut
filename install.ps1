$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

Write-Host "=== Sovereign Cut 2.0 MVP install ===" -ForegroundColor Cyan

if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python не найден в PATH. Поставь Python 3.11+ и повтори."
}

if (!(Test-Path ".\.venv")) {
    python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "ffmpeg не найден в PATH." -ForegroundColor Yellow
    Write-Host "Проще всего поставить так:" -ForegroundColor Yellow
    Write-Host "winget install Gyan.FFmpeg" -ForegroundColor Green
    Write-Host "После установки перезапусти PowerShell и снова запусти run.ps1" -ForegroundColor Yellow
} else {
    Write-Host "ffmpeg найден." -ForegroundColor Green
}

Write-Host "Готово. Запуск: .\run.ps1" -ForegroundColor Green
