# PEKAT Inspection Tool - V03 Preview Release Notes

## Scope
- Context-driven evaluation feedback aligned with PEKAT API behavior.
- New runtime counters and JSON inspection tab in GUI.
- REST parser hardening for context transport variants.
- V03.1 file post-processing (delete/move by evaluation result).
- V03.2 output artifacts (JSON context + processed image).

## Major Changes
- Added context normalization module: `pektool/core/context_eval.py`.
- Added normalized evaluation model: `pektool/types.py`.
- Extended runtime stats in `ConnectionManager`:
  - sent/evaluated counters
  - OK/NOK counters
  - last and average evaluation time
  - last full result JSON snapshot
- Updated `Runner` to:
  - normalize context result using `result` and `completeTime`
  - fallback to `result_field`
  - write extended JSONL records
- Updated REST client:
  - raw numpy path routed to `/analyze_raw_image?height=&width=`
  - improved context parsing robustness (`ImageLen`, `ContextBase64utf`)
- Updated GUI:
  - new `Last Context JSON` tab with last full context
  - last/average evaluation time fields
  - large OK/NOK counters
  - reset now resets all runtime counters and JSON snapshot
  - file manipulation tab with shared OK/NOK folder and naming rules
  - output artifact toggles:
    - `Ukladat JSON Context`
    - `Save PROCESSED Image`

## Config Additions
- `pekat.oknok_source: context_result | result_field` (default `context_result`)
- `file_actions.enabled`
- `file_actions.mode`
- `file_actions.save_json_context`
- `file_actions.save_processed_image`
- `file_actions.processed_response_type` (default `annotated_image`)

## Validation
- Automated tests (latest): `33 passed, 1 skipped`
- Added tests across:
  - context normalization
  - REST context/image parsing
  - SDK result extraction
  - file action engine
  - artifact saver
  - runner integration for file actions and artifacts

## Notes
- Branch: `v03`
- Stable tag is intentionally not created in this preview phase.
