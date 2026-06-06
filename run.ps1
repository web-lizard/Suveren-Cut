$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$Port = 8517
$VenvPython = ".\.venv\Scripts\python.exe"

$Busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($Busy) {
    $PidOwner = $Busy[0].OwningProcess
    $Proc = Get-Process -Id $PidOwner -ErrorAction SilentlyContinue
    throw "Port $Port is busy: PID=$PidOwner Process=$($Proc.ProcessName)"
}

if (!(Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found. Creating..." -ForegroundColor Yellow
    python -m venv .venv
}

& $VenvPython -m pip install -r requirements.txt

$FfmpegPath = & $VenvPython -c "from suveren_cut.ffmpeg_tools import get_ffmpeg_exe; print(get_ffmpeg_exe())"
if (!$FfmpegPath) {
    throw "Bundled ffmpeg was not found."
}

Write-Host "ffmpeg: $FfmpegPath" -ForegroundColor Green
Write-Host "Sovereign Cut 2.3 starts at http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Stop server: Ctrl + C" -ForegroundColor Yellow

& $VenvPython -m streamlit run app.py --server.port $Port --server.address localhost
