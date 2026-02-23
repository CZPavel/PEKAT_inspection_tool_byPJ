# PEKAT Inspection Tool - Technical Overview (v3.6)

This document describes architecture and runtime behavior of the tool.

Dependency map for release packaging and runtime module flow:
- `docs/DEPENDENCY_LINKS.md`

## Architecture

The app is split into four layers:

1. UI/CLI layer - input, validation, persistence
2. Connection layer - connect, ping, PM TCP control, runtime stats
3. Runner layer - file scan, queue, analyze pipeline
4. Client layer - REST, SDK, PM TCP

## Core Modules

### `pektool/core/connection.py`
- Connection states: `disconnected | connecting | connected | reconnecting | error | disconnecting`
- Builds REST or SDK client and executes health checks
- PM TCP policies: `off | auto_start | auto_start_stop | auto_restart`
- Stores runtime counters:
  - `total_sent`
  - `total_evaluated`
  - `ok_count`
  - `nok_count`
  - `last_eval_time_ms`
  - `avg_eval_time_ms`
  - `last_result_json`
- `reset_counters()` resets all counters and JSON snapshot
- Production mode parsing checks key variants:
  - `Production_Mode`, `production_mode`, `ProductionMode`, `productionMode`, `production mode`

### `pektool/core/runner.py`
- Polls files, enqueues tasks, processes queue
- Sends image + `data` into PEKAT
- Normalizes context evaluation result for UI/logs
- Writes JSONL per image with status and evaluation details
- Supports run modes:
  - `loop`
  - `once`
  - `initial_then_watch`
  - `just_watch` (ignores startup files and sends only newly created files)
- Applies optional post-evaluation file actions (delete/move)
- In `loop` mode, file actions are force-disabled with warning log
- In `sound camera` mode (`audio.enabled=true`):
  - file scanner is not started
  - sound camera engine feeds queue with generated frames (`Path` in `save_send`, `numpy` in `send_only`)
  - worker pipeline remains unchanged (analyze + file actions + artifacts)
  - source move/delete actions are auto-disabled in `send_only`
- Supports preview callback hook for GUI live preview without second capture stream
- Can save output artifacts after evaluation:
  - JSON context file
  - processed image file
- If processed saving is enabled, analyze call uses `annotated_image`

### `pektool/core/sound_camera/*`
- `audio_sources.py`:
  - `Loopback | Microphone | Sine` source implementations
  - Windows fallback chain:
    - `pyaudiowpatch` WASAPI loopback
    - `sounddevice` WASAPI loopback
    - Stereo Mix / loopback-like input
- `engine.py`:
  - captures audio windows and renders selected approach
  - handles `save_send` and `send_only`
  - on render error emits explicit error frame (prevents stale preview image)
- `render_payload.py`, `render_lissajous.py`, `render_classic.py`, `render_fuse7.py`:
  - three rendering approaches with per-approach parameters
  - `lissajous` supports `tau=both` side-by-side composition (`2W`)
  - `classic` exposes dependency capability check (`classic_dependencies_status`) and validates STFT params (`hop_ms <= win_ms`, positive limits)
  - `classic` style routing:
    - `style=classic` -> `render_classic.py` with `axis_mode=linear|log|mel`
    - `style=fuse7|fuse4_base` -> `render_fuse7.py` with reference mel fusion pipeline
- `preview_controller.py`:
  - standalone preview lifecycle independent from sender
  - supports runtime `reconfigure` (`stop -> start`) with queue reset

### `pektool/core/file_actions.py`
- Centralized post-processing logic for source files
- Modes:
  - `delete_after_eval`
  - `move_by_result`
  - `move_ok_delete_nok`
  - `delete_ok_move_nok`
- Evaluation routing:
  - `OK` stays `OK`
  - `NOK` stays `NOK`
  - `UNKNOWN/ERROR` treated as `NOK`
- Target path builder:
  - root target dir
  - optional daily folder `YYYY_MM_DD`
  - optional hourly folder `MM_DD_HH`
- Filename builder:
  - optional result prefix (`OK_`/`NOK_`)
  - optional timestamp suffix (`_YYYY_MM_DD_HH_MM_SS`)
  - optional custom string suffix
- Collision handling:
  - auto-rename (`_1`, `_2`, ...)
- Fail-safe behavior:
  - returns structured result instead of raising fatal exception

### `pektool/core/artifact_saver.py`
- Saves optional artifacts after successful analysis.
- Uses the same OK/NOK routing and folder/naming settings as file actions.
- JSON context:
  - pretty UTF-8 JSON (`indent=2`)
  - file extension `.json`
- Processed image:
  - file extension `.png`
  - default base stem `ANOTATED_<original_stem>`
- Name collision handling uses auto-rename (`_1`, `_2`, ...).

### `pektool/core/context_eval.py`
- Converts PEKAT context into normalized evaluation object
- Primary OK/NOK source:
  - `context.result` when `pekat.oknok_source=context_result`
- Fallback source:
  - `pekat.result_field` path in context
- Time source:
  - `context.completeTime` (seconds) -> `complete_time_ms`
  - fallback to measured client latency
- Detection summary:
  - `detected_count = len(context.detectedRectangles)` when list is present

### `pektool/clients/rest_client.py`
- Analyze endpoints:
  - `POST /analyze_image` for PNG/file/bytes
  - `POST /analyze_raw_image?height=&width=` for numpy arrays
- Optional URL params:
  - `response_type`
  - `data`
  - `context_in_body`
- Context parsing modes:
  - `response_type=context` -> `response.json()`
  - `context_in_body=false` -> `ContextBase64utf`
  - `context_in_body=true` -> split body using `ImageLen`
  - fallback to `response.json()` when image/context headers are missing
- Returns both parsed context and image bytes for image response types.
- Utility endpoints used:
  - `GET /ping`

### `pektool/clients/tcp_controller.py`
- Projects Manager TCP commands with preferred syntax:
  - `command|<project_path>`
- Supports legacy fallback:
  - `command:<project_path>`
- Handles `suc:` / `err:` response prefixes

### `pektool/core/port_info.py`
- Provides data model for PEKAT port diagnostics:
  - `KnownPortEntry`
  - `PortScanResult`
- Collects local listeners using:
  - PowerShell `Get-NetTCPConnection` (primary)
  - `netstat -ano` fallback
- Resolves PID -> process name using:
  - PowerShell `Get-Process` JSON (primary)
  - `tasklist` fallback
- Probes PEKAT ownership signals:
  - PM HTTP `/projects/list` (port 7000 by default)
  - PM TCP probe (port 7002 when enabled)
  - project `/ping` endpoint
- Supports:
  - common port checks (7000, 7002, 8000, 1947)
  - occupied-only range scan for 8000-8100
  - basic local network summary text (`get_basic_network_info`)

### `pektool/core/tuning_catalog.py`
- Manages script catalog storage for PEKAT Code module helpers.
- Creates and maintains:
  - `resources/code_modules/scripts_raw`
  - `resources/code_modules/scripts_utf8`
  - `resources/code_modules/pmodule`
  - `resources/code_modules/catalog.json`
- Import pipeline:
  - UTF-8 decode first
  - fallback cp1250/latin1
  - canonical UTF-8 copy + raw copy
- Replace import mode:
  - `replace_from_folder(...)` clears previous catalog/storage content
  - imports only current source folder set
  - skips empty files when `skip_empty=true`
- Metadata enrichment:
  - parses XLSX overview (`Soubor`, `Kategorie`, `K cemu slouzi`, `Co dela`, `Klicove context`, `Zavislosti`)
  - merges supplemental TXT descriptions
  - applies manual metadata overrides for specific scripts (for example pyzbar barcode reader)
  - metadata priority: `xlsx -> txt -> manual -> generated`
  - generates fallback metadata when source metadata is missing
- Supports listing/filtering/search and exporting scripts.

### `pektool/core/library_installer.py`
- Loads library install manifest from:
  - `resources/pekat_libs/<lib>/install_manifest.json`
- Builds dry-run install plan (new/overwrite/size).
- Validates PEKAT target path (`<PEKAT_ROOT>/server`).
- Executes copy with optional backup:
  - `logs/installer/installer_backups/<timestamp>`
- Includes tasklist-based running process hint.
- Selects default PEKAT root by numeric version sort of `PEKAT VISION x.y.z`.
- Validates offline payload against manifest (`validate_manifest_payload`) for pre-check reporting.

## Data Flow

1. UI/CLI builds `AppConfig`
2. `ConnectionManager.connect()` initializes client and verifies connectivity
3. `Runner` scans files and enqueues `ImageTask`
4. Worker sends image and receives context
5. Context is normalized (`context_eval`)
6. Runtime counters and JSON snapshot are updated
7. JSONL and text logs are written

## V03 GUI Feedback Data

Displayed values:
- `Odeslano` -> `total_sent`
- `Posledni vyhodnoceni (ms)` -> `last_eval_time_ms`
- `Prumerny cas (ms)` -> `avg_eval_time_ms`
- `OK` and `NOK` counters
- Full JSON of last processed image in dedicated `Last Context JSON` tab

## v3.6 Pekat Tuning + Pekat Info GUI tabs

`Pekat Tuning` tab:
1. Script Catalog section:
   - table + search + category filter
   - script preview
   - columns aligned to source spreadsheet:
     - `Soubor`, `Kategorie`, `K cemu slouzi`, `Co dela`, `Klicove context`, `Zavislosti`
   - clipboard/export/storage actions
   - destructive sync button:
     - `Nahradit skripty ze zdroje`
     - shows summary `imported / skipped empty / source`
   - full generated script overview document:
     - `docs/PEKAT_CODE_SCRIPT_CATALOG.md`
2. Library Installer section:
   - pyzbar install wizard
   - ONNX Runtime + Real-ESRGAN install wizard (fallback path copy)
   - pre-check includes target validity, write access, running process hint, missing payload files

`Pekat Info` tab is read-only diagnostics and does not modify project state.

Main blocks:
1. Common PEKAT ports table:
   - description
   - links
   - last status
   - ownership classification
2. Active scan controls:
   - `Check common ports`
   - `Scan range 8000-8100`
3. Useful links section.
4. PC network settings section:
   - refreshed when user opens `Pekat Info` tab
   - focuses on adapter properties: adapter name, MAC, IPv4/subnet mask, network/profile name
   - rendered as side-by-side adapter cards
   - sorting pushes Wi-Fi and Bluetooth adapters to the end

Port ownership classification order:
1. PM HTTP confirmed
2. PM TCP confirmed
3. Running PM project by matching `projects/list` port
4. `GET /ping` success (`PEKAT project/API likely`)
5. process-name hint (`pekat`)
6. fallback to `Other` / `Unknown`

Port `1947` is included as licensing/update port for this installation context.

## Config Notes

Important keys in `configs/config.example.yaml`:
- `pekat.oknok_source: context_result | result_field`
- `pekat.result_field` (fallback path)
- `pekat.response_type`, `pekat.context_in_body`
- `file_actions.save_json_context`
- `file_actions.save_processed_image`
- `file_actions.processed_response_type` (`annotated_image`)
- PM TCP settings under `projects_manager` and `connection`
- Sound camera settings under `audio`:
  - `enabled`
  - `approach` (`payload | lissajous | classic`)
  - `classic.style` (`classic | fuse7 | fuse4_base`)
  - `classic.axis_mode` (`linear | log | mel`, used only when `style=classic`)
  - `source` (`loopback | microphone | sine`)
  - `backend_policy` (`auto | prefer_pyaudiowpatch | sounddevice_only`)
  - `send_mode` (`save_send | send_only`)
  - `device_name`
  - `sample_rate_hz`
  - `window_sec`
  - `fps` (alias, mapped to `interval_sec = 1/fps`)
  - `interval_sec`
  - `snapshot_dir`
  - `file_prefix`
  - nested sections: `payload`, `lissajous`, `classic`
  - timing validation is approach-dependent:
    - `payload/lissajous`: `interval_sec >= window_sec`
    - `classic`: overlap allowed (`interval_sec < window_sec`)

GUI runtime guard:
- before `Start preview` / `Start sending`, `classic` mode checks `scipy` availability and blocks action with install hint when missing.

## Logging

- `logs/app.log` for system/runtime messages
- `logs/results.jsonl` for per-image records containing:
  - status, latency, eval_status, result_bool, complete_time, detected_count
  - file action fields:
    - `file_action_applied`
    - `file_action_operation`
    - `file_action_target`
    - `file_action_reason`
  - artifact fields:
    - `json_context_saved`
    - `json_context_path`
    - `processed_image_saved`
    - `processed_image_path`
    - `artifact_reason`

## Constraints

- `data` is internal PEKAT argument and usually is not returned by REST response
- PM HTTP (`7000`) provides list/status, not start/stop
- PM TCP control works only if TCP server is enabled in Projects Manager

