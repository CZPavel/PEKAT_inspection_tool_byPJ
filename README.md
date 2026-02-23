# PEKAT Inspection Tool (v3.6)

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
- in `Sound camera + Send-only`, source move/delete actions are disabled automatically

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

## Sound camera (v3.6)
GUI tab `Sound camera` replaces legacy `Audio / Mikrofon`.

Supported approaches:
- `Payload`
- `Lissajous`
- `Classic`

Classic styles:
- `CLASSIC` (linear STFT spectrogram)
- `FUSE7` (specialized color fusion view from lab reference)
- `FUSE4_base` (base hue+edge composition)

Classic Y-axis mode:
- `Linear | Log | Mel` (applies only to `CLASSIC` style)
- FUSE styles keep reference mel logic without axis remap

Supported sources:
- `Loopback` (Windows output capture)
- `Microphone`
- `Sine` (test generator)

Send modes:
- `Save+Send`: save PNG snapshot and send file path
- `Send-only`: send in-memory frame directly (SDK has temporary PNG fallback if needed)
- both modes send exactly one selected style image per frame

Preview:
- standalone preview window can run without `Start sending`
- during active sending, preview switches to runner frame callback (single capture stream)

Windows capture fallback chain:
- `pyaudiowpatch` WASAPI loopback (preferred)
- `sounddevice` WASAPI loopback
- Stereo Mix / loopback-like input fallback

Detailni nastaveni a profily:
- `docs/SOUND_CAMERA.md`

## Pekat Tuning tab (v3.6)
GUI tab `Pekat Tuning` provides two sections:

1) Code Module Script Catalog
- central storage under `resources/code_modules`
- destructive sync from predefined source folder `C:\VS_CODE_PROJECTS\SCRIPTY_PEKAT_CODE`
- old catalog items are deleted during replace sync
- script list with search and category filter
- UTF-8 preview of selected script
- actions:
  - `Nahradit skripty ze zdroje`
  - `Refresh catalog`
  - `Copy as text`
  - `Export selected...`
  - `Open storage folder`
- table columns are aligned with spreadsheet structure:
  - `Soubor`
  - `Kategorie`
  - `K cemu slouzi`
  - `Co dela`
  - `Klicove context`
  - `Zavislosti`
- metadata sources:
  - XLSX overview in source folder
  - supplemental TXT description in source folder
  - manual metadata override for selected scripts (e.g. `PYZBAR_BARCODE_READER.txt`)
  - generated fallback when metadata is missing
- empty script files are skipped during sync
- synchronized catalog list is documented in `docs/PEKAT_CODE_SCRIPT_CATALOG.md`

2) Library Installer
- wizard-based install flow for PEKAT extension libraries
- first implemented package: `pyzbar`
- default path targets numerically newest `C:\Program Files\PEKAT VISION x.y.z`
- pre-check includes path validity, write access, running-process hint and offline payload completeness
- dry-run preview before copy
- optional backup before overwrite
- placeholder buttons reserved for future libraries

Bundled pyzbar payload is stored in:
- `resources/pekat_libs/pyzbar/payload`
- manifest: `resources/pekat_libs/pyzbar/install_manifest.json`

## Pekat Info tab (v3.6)
GUI tab `Pekat Info` provides:
- common PEKAT port overview with short description and clickable links
- status check for common ports:
  - 7000 (Projects Manager HTTP list + PM UI link)
  - 7002 (Projects Manager TCP)
  - 8000 (project typical API test + project root)
  - 1947 (licensing/update port for this setup)
- range scan for project ports `8000-8100`
- occupied port details:
  - listening state
  - PID and process name
  - best-effort classification (`PEKAT project`, `PEKAT PM HTTP`, `PEKAT PM TCP`, `Other`, ...)
- adapter-oriented local network section loaded when tab is opened
  - cards shown side by side
  - Wi-Fi and Bluetooth adapters are intentionally listed at the end

Useful links section includes:
- PEKAT homepage
- PEKAT KB 3.19 Home
- PEKAT GitHub

## File Manipulation (V03.1+)
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
- `dist/PEKAT_Inspection_tool_by_PJ_V03_6/pektool-gui.exe`
- `dist/PEKAT_Inspection_tool_by_PJ_V03_6/pektool.exe`

`resources/` directory is bundled into PyInstaller output for runtime catalog and installer assets.

## Release 3.6 artefakty a návaznosti
- Release souhrn:
  - `docs/RELEASE_3_6.md`
- Uživatelský návod:
  - `docs/USER_GUIDE.md`
- Technický přehled:
  - `docs/TECHNICAL_OVERVIEW.md`
- Sound camera reference:
  - `docs/SOUND_CAMERA.md`
- Mapa návazností modulů:
  - `docs/DEPENDENCY_LINKS.md`

## Forward backlog
- Follow-up plan is tracked in `docs/NEXT_STEPS.md` for next development iteration.
- Current priorities: user acceptance test of v3.6 and script description cleanup.


