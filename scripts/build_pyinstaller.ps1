$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Error "PyInstaller not found. Install it with: pip install pyinstaller"
}

# Build uses:
# - EXE icon: resources/branding/pektool-ico.ico
# - Output folder: dist/PEKAT_Inspection_tool_by_PJ_V03_6
pyinstaller --clean --noconfirm pyinstaller.spec
