# PEKAT Inspection Tool - Technical Overview (V03)

This document describes architecture and runtime behavior of the tool.

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

### `pektool/core/runner.py`
- Polls files, enqueues tasks, processes queue
- Sends image + `data` into PEKAT
- Normalizes context evaluation result for UI/logs
- Writes JSONL per image with status and evaluation details

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
- Utility endpoints used:
  - `GET /ping`

### `pektool/clients/tcp_controller.py`
- Projects Manager TCP commands with preferred syntax:
  - `command|<project_path>`
- Supports legacy fallback:
  - `command:<project_path>`
- Handles `suc:` / `err:` response prefixes

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
- Full JSON of last processed image in dedicated `JSON` tab

## Config Notes

Important keys in `configs/config.example.yaml`:
- `pekat.oknok_source: context_result | result_field`
- `pekat.result_field` (fallback path)
- `pekat.response_type`, `pekat.context_in_body`
- PM TCP settings under `projects_manager` and `connection`

## Logging

- `logs/app.log` for system/runtime messages
- `logs/results.jsonl` for per-image records containing:
  - status, latency, eval_status, result_bool, complete_time, detected_count

## Constraints

- `data` is internal PEKAT argument and usually is not returned by REST response
- PM HTTP (`7000`) provides list/status, not start/stop
- PM TCP control works only if TCP server is enabled in Projects Manager
