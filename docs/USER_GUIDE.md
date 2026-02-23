# PEKAT Inspection Tool - User Guide (v3.6)

This guide describes GUI controls and runtime indicators.

## Main Tab: Konfigurace

### 1) Mode (SDK/REST)
- Default: `REST`
- Use `SDK` only when SDK runtime is available and intended

### 2) Host / Port
- Target project host and port
- Default: `127.0.0.1` and `8000`

### 3) Project path
- Required only for PM TCP project control

### 4) Input source
- `Slozka` for folder mode
- `Zahrnout podslozky` for recursive scan
- `Vybrat soubory` for fixed file list mode

### 5) Run mode
- `Loop`: Nacita snimky k vyhodnoceni stale dokola
- `Once`: Odesle postupne vsechny snimky k vyhodnoceni jen jednou
- `Send ALL Once and Watch`: Odesle vsechny snimky ve slozce jednou, pak ceka na dalsi nove
- `Just Watch`: Ignoruje stavajici snimky ve slozce a ceka jen na nove soubory

Poznamka:
- Vsechny rezimy respektuji volbu `Zahrnout podslozky`.

### 6) Delay
- `Prodleva (ms)` is delay between sends

### 7) Data payload options
- `Include filename`
- `Include timestamp`
- `Include string`

Result is sent as a single `data` string in REST/SDK analyze call.

### 8) API key setup
- Open dialog with `API key setup`
- Keep empty if secure analyze is not enabled in project

### 9) Project control (PM TCP)
- `PM TCP enabled`
- PM host/port (typically `7002`)
- Policy:
  - `Off (status only)`
  - `Auto-start on Connect`
  - `Auto-start + Auto-stop on Disconnect`
  - `Automatic restart`

Notes:
- Works only when PM TCP server is enabled in Projects Manager settings.
- `start/stop` may return no immediate response (timeout); app tracks state through `status`.

### 10) Control buttons
- `Connect`
- `Disconnect`
- `Start sending`
- `Stop sending`

## Runtime Indicators

- `Connection`: current connection state
- `Sending`: sender state
- `Production Mode`: ON/OFF/Unknown from last context
- `Data preview`: last sent `data`
- `Odeslano`: total sent images
- `Posledni vyhodnoceni (ms)`: time of last evaluated image
- `Prumerny cas (ms)`: average evaluation time
- `NOK` and `OK`: large counters in bottom panel

## Tabs

- `Manipulace se soubory`: post-evaluation delete/move rules
- `Last Context JSON`: full JSON of last processed image context (or last error payload)
- `Pekat Tuning`: script catalog and PEKAT library installer
- `Sound camera`: zvukova kamera (Payload/Lissajous/Classic) s preview oknem
- `Pekat Info`: local PEKAT port overview, port scan, and useful links
- `Log`: runtime log stream

## Tab: Sound camera

Spolecne prvky:
- `Povolit Sound camera`
- `Pristup`: `Payload | Lissajous | Classic`
- `Zdroj`: `Loopback | Microphone | Sine`
- `Backend policy`: `Auto | Prefer pyaudiowpatch | Pouze sounddevice`
- `Rezim odesilani`: `Save+Send | Send-only`
- `Sample rate`, `Delka snimku`, `Interval`
- `Sine frequency` (aktivni jen pro `Sine`)
- `Snapshot slozka` + `Prefix souboru` (povinne pouze v `Save+Send`)

Approach-specific pages:
- `Payload`: `frame_seconds`, `overlap`, `style_mode`, `y_repeat`, `variant`, `preview_resize`
- `Lissajous`: `tau`, `width`, `height`, `accum`, `point_size_step`, `point_render_style`, `value_mode`, `rotation`
- `Classic`: `preset`, `W`, `H`, `colormap`, `gamma`, `detail_mode`, `detail_sigma`, `detail_gain`, `detail_p`, `freq_interp`

Preview:
- `Start preview`: spusti nezavisly preview i bez `Start sending`
- `Stop preview`
- `Ukazat preview`: otevre separaâ€‹tni okno s live obrazem, metadaty a snapshot tlacitkem
- Pri aktivnim `Start sending` je nezavisly preview zastaven a okno bere data z runner callbacku (bez druheho capture streamu)

Windows audio capture fallback:
- primarne `pyaudiowpatch` WASAPI loopback
- fallback `sounddevice` WASAPI
- fallback Stereo Mix / loopback-like input

Send mode behavior:
- `Save+Send`: frame se ulozi jako PNG a odesila se z ulozeneho souboru
- `Send-only`: frame se odesila primo in-memory, zdrojove move/delete akce jsou vypnute, artifacty (JSON/processed) mohou zustat zapnute

## Tab: Pekat Tuning

The tab has two sections.

### 1) Code Module Script Catalog
- Script storage is kept inside app tree:
  - `resources/code_modules/scripts_raw`
  - `resources/code_modules/scripts_utf8`
  - `resources/code_modules/pmodule`
  - `resources/code_modules/catalog.json`
- Source folder default:
  - `C:\VS_CODE_PROJECTS\SCRIPTY_PEKAT_CODE`
- Use `Nahradit skripty ze zdroje` for destructive synchronization (replace, not append).
- Supported formats:
  - `.txt`
  - `.py`
  - `.pmodule` (metadata cataloging for now)

Catalog behavior:
- text files are decoded using UTF-8 first, then cp1250/latin1 fallback
- canonical UTF-8 copy is created for preview/copy
- raw source copy is preserved for traceability
- old catalog entries are deleted on replace sync
- empty files are skipped

Table columns:
- `Soubor`
- `Kategorie`
- `K cemu slouzi`
- `Co dela`
- `Klicove context`
- `Zavislosti`

Metadata source priority:
1. `Prehled scriptu pro PEKAT CODE modul.xlsx`
2. `Popis funkcionalit a urceni scriptu.txt`
3. Manual override metadata (selected scripts, e.g. `PYZBAR_BARCODE_READER.txt`)
4. Generated fallback description

Full synchronized script list:
- `docs/PEKAT_CODE_SCRIPT_CATALOG.md`

Available actions:
- `Refresh catalog`
- `Copy as text`
- `Export selected...`
- `Open storage folder`

### 2) Library Installer
- `Install pyzbar` starts guided installation wizard.
- `Install ONNX Runtime + Real-ESRGAN` starts guided fallback wizard for offline CPU upscaling bundle.

Wizard flow:
1. warning page
2. PEKAT path selection (expects `...\\server`)
3. pre-check (write access and running process hint)
4. dry-run summary (files/new/overwrite/size)
5. execute install with optional backup

Install source:
- `resources/pekat_libs/pyzbar/payload`
- `resources/pekat_libs/onnxruntime_realesrgan/payload`

Related docs:
- `docs/LIB_INSTALLER_PYZBAR.md`
- `docs/LIB_INSTALLER_ONNXRUNTIME_REALESRGAN.md`
- `docs/PEKAT_AI_UPSCALING_PLAN.md`

Important:
- Preferred production deployment for ONNX Runtime is outside Program Files (`C:\ProgramData\PEKAT\pydeps`) and loaded via `sys.path` in Code module.
- Wizard copy to `...\\server` is fallback strategy.

Default PEKAT path:
- installer picks the newest `C:\Program Files\PEKAT VISION x.y.z` by numeric version

Backup location:
- `logs/installer/installer_backups/<timestamp>`

## Tab: Pekat Info

The tab has three sections.

### 1) Common PEKAT ports
Shows frequently used ports and ranges:
- `7000`: Projects Manager HTTP (`/projects/list`)
- `7002`: Projects Manager TCP control
- `8000`: typical project API port
- `8000-8100`: project scan range used by this tool
- `1947`: licensing/update port (configured for this setup)

Each row includes:
- short purpose text
- clickable URL link
- last checked status
- ownership classification

### 2) Port status check
Buttons:
- `Check common ports`
- `Scan range 8000-8100`

Output table shows:
- port
- listening state
- PID
- process name
- ownership classification
- detail text

Ownership is best-effort and can be:
- `PEKAT PM HTTP`
- `PEKAT PM TCP`
- `PEKAT project`
- `PEKAT project/API likely`
- `PEKAT related`
- `Other`
- `Unknown`

### 3) Useful links
Quick links to:
- PEKAT homepage
- PEKAT KB 3.19 Home
- PEKAT GitHub

### 4) PC network settings
- A basic adapter-focused network summary is shown at the bottom of the tab.
- The data is loaded automatically when you switch to `Pekat Info`.
- Adapter sections are shown side by side.
- Wi-Fi and Bluetooth adapters are listed at the end.
- Typical fields:
  - adapter name
  - MAC address
  - IPv4 address and subnet mask
  - connected network name/profile (when available)

## Tab: Manipulace se soubory

### 1) Enable
- `Povolit manipulaci se soubory` turns post-processing on/off
- In `Loop` run mode, this checkbox is disabled and forced OFF (vyjimka: aktivni `Sound camera`)
- Message in loop mode (without audio): `V rezimu Loop neni dostupna manipulace se zdrojovymi soubory.`
- New independent options:
  - `Ukladat JSON Context`
  - `Save PROCESSED Image`
- These two options can remain enabled even in `Loop` mode.

### 2) Manipulation mode
- `Po vyhodnoceni mazat soubory`
- `Presouvat podle vyhodnoceni`
- `Presun kdyz OK - Smaz kdyz NOK`
- `Smaz kdyz OK - Presun kdyz NOK`

### 3) Section OK / Section NOK
Each section contains:
- target folder path
- folder picker button
- `Vytvorit novou slozku pro kazdy den (YYYY_MM_DD)`
- `Vytvorit novou slozku pro kazdou hodinu (MM_DD_HH)`
- `Include RESULT` (`OK_` / `NOK_` prefix)
- `Include Timestamp` (`_YYYY_MM_DD_HH_MM_SS` suffix)
- `Include String` + custom text field

Rules:
- If both daily and hourly are enabled, hourly folder is created under daily folder.
- If only hourly is enabled, hourly folder is created directly under target root.
- Unknown or error evaluation is treated as `NOK` for routing.
- Name collisions in target folder use auto-rename (`_1`, `_2`, ...).
- JSON context file is saved as `.json` with image-derived name.
- Processed image is saved as `.png` and default stem starts with `ANOTATED_`.
- Example: `part_001.png` -> `ANOTATED_part_001.png`.

## Reset

`Reset counter and list` resets all runtime counters:
- sent count
- last/average evaluation time
- OK/NOK counters
- sent list
- JSON snapshot (to default state)

## Recommended Workflow

1. Configure host/port and input
2. Optional: configure PM TCP + policy
3. Click `Connect`
4. Click `Start sending`
5. Monitor `Log`, `JSON`, and counters

## Troubleshooting

- If reconnect loops appear, verify project is running on expected host/port.
- For PM control issues, verify PM TCP is enabled and project path is valid.
- `data` is internal project argument; it is used inside PEKAT flow and is not usually returned in REST response.

