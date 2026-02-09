$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Error "PyInstaller not found. Install it with: pip install pyinstaller"
}

pyinstaller --clean --noconfirm pyinstaller.spec
