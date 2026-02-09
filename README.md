# PEKAT Inspection Tool

Python aplikace (CLI + GUI) pro odesílání snímkù do PEKAT VISION 3.19.x pøes SDK nebo REST API.

## Požadavky
- Python 3.8+
- PEKAT VISION 3.19.x
- Windows 10/11 nebo Linux

## Instalace
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -e .
```

## Konfigurace
Upravte `configs/config.example.yaml` podle svého prostøedí.

## Spuštìní
### CLI
Batch zpracování složky:
```powershell
pektool run --config configs/config.example.yaml
```

Sledování nové produkce:
```powershell
pektool run --config configs/config.example.yaml --run-mode initial_then_watch
```

Poslání vybraných souborù:
```powershell
pektool run --files D:\img\a.png D:\img\b.jpg
```

Ping:
```powershell
pektool ping --config configs/config.example.yaml
```

Projects Manager:
```powershell
pektool pm status --project "C:\path\to\project"
pektool pm list --base-url http://127.0.0.1:7000
```

### GUI
```powershell
pektool-gui
```

## Build (PyInstaller, single-file)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_pyinstaller.ps1
```

Výstupy budou v `dist/`.