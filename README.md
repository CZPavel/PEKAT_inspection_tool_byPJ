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

Important V03.1 file manipulation options:
- `file_actions.enabled`
- `file_actions.mode: delete_after_eval | move_by_result | move_ok_delete_nok | delete_ok_move_nok`
- `file_actions.ok.*` and `file_actions.nok.*` for target folders and naming

Important V03.2 artifact options:
- `file_actions.save_json_context`
- `file_actions.save_processed_image`
- `file_actions.processed_response_type` (default `annotated_image`)

Note:
- `data` is internal PEKAT argument used inside project flow.
- PM TCP control works only when TCP server is enabled in Projects Manager.
- file manipulation is automatically disabled in `run_mode=loop`
- `UNKNOWN/ERROR` evaluations are treated as `NOK` for file manipulation routing
- in `run_mode=loop`, JSON context / processed image saving can stay enabled

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
- full JSON context of last processed image in `Last Context JSON` tab

## File Manipulation (V03.1)
GUI tab `Manipulace se soubory` supports post-evaluation actions:
- delete evaluated files
- move by result (OK/NOK)
- move OK + delete NOK
- delete OK + move NOK

V03.2 adds artifact outputs in the same tab:
- `Ukladat JSON Context`
- `Save PROCESSED Image`

Folder and filename rules:
- daily folder: `YYYY_MM_DD`
- hourly folder: `MM_DD_HH`
- when daily+hourly are both enabled, hourly is nested under daily
- optional filename modifiers:
  - result prefix (`OK_` / `NOK_`)
  - timestamp suffix (`_YYYY_MM_DD_HH_MM_SS`)
  - custom string suffix
- on target name collision, auto-rename is used (`_1`, `_2`, ...)
- processed image default naming uses prefix `ANOTATED_`:
  - `part_001.png` -> `ANOTATED_part_001.png`

## Build (PyInstaller onedir)
```powershell
pyinstaller --clean --noconfirm pyinstaller.spec
```

Build output:
- `dist/PEKAT_Inspection_tool_by_PJ/pektool-gui.exe`
- `dist/PEKAT_Inspection_tool_by_PJ/pektool.exe`
