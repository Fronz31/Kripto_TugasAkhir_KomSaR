# Build KomSaR.exe (onedir, tanpa konsol). Jalankan dari folder mana pun.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m PyInstaller --noconfirm --clean --onedir -w --name KomSaR main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller gagal" }

Copy-Item config.example.json dist\KomSaR\config.example.json -Force
Write-Host "Selesai: dist\KomSaR\KomSaR.exe (salin config.example.json menjadi config.json)"
