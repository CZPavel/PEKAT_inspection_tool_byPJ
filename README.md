# PEKAT Inspection Tool

Python app (CLI + GUI) for sending images to PEKAT VISION 3.19.x through SDK or REST API.

## Requirements
- Python 3.8+
- PEKAT VISION 3.19.x
- Windows 10/11 or Linux

## Install
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -e .
```

## Configuration
Edit `configs/config.example.yaml` for your environment.

Important REST options:
- `rest.api_key`
- `rest.api_key_location`
- `rest.api_key_name`

Important V03 evaluation options:
- `pekat.oknok_source: context_result | result_field`
- `pekat.result_field` (fallback)
- `pekat.response_type`
- `pekat.context_in_body`
- `behavior.run_mode: loop | once | initial_then_watch | just_watch`

Note:
- `data` is internal PEKAT argument used inside project flow.
- PM TCP control works only when TCP server is enabled in Projects Manager.

## Run
### CLI
```powershell
pektool run --config configs/config.example.yaml
```

```powershell
pektool run --config configs/config.example.yaml --run-mode initial_then_watch
```

```powershell
pektool run --files D:\img\a.png D:\img\b.jpg
```

```powershell
pektool ping --config configs/config.example.yaml
```

```powershell
pektool pm status --project "C:\path\to\project"
pektool pm list --base-url http://127.0.0.1:7000
```

### GUI
```powershell
pektool-gui
```

## V03 Feedback Metrics
GUI shows:
- sent count
- last evaluation time (ms)
- average evaluation time (ms)
- NOK/OK counters
- full JSON context of last processed image in `JSON` tab

## Build (PyInstaller onedir)
```powershell
pyinstaller --clean --noconfirm pyinstaller.spec
```

Build output:
- `dist/PEKAT_Inspection_tool_by_PJ/pektool-gui.exe`
- `dist/PEKAT_Inspection_tool_by_PJ/pektool.exe`
