# Build KomSaR.exe (satu file, tanpa konsol). Jalankan dari folder mana pun.
# Bila config.json ada di folder ini, URL server ikut ditanam di dalam exe sebagai default.
Set-Location $PSScriptRoot

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
$extra = @()
if (Test-Path "config.json") { $extra = @("--add-data", "config.json;.") }
# PyInstaller menulis log INFO ke stderr; jangan jadikan error di PowerShell 5.1.
& $py -m PyInstaller --noconfirm --clean --onefile -w --name KomSaR --icon KomSaR.ico @extra main.py 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw "PyInstaller gagal" }

Write-Host "Selesai: dist\KomSaR.exe"
