# PEKAT Inspection Tool - V03 Preview Release Notes

## Scope
- Context-driven evaluation feedback aligned with PEKAT API behavior.
- New runtime counters and JSON inspection tab in GUI.
- REST parser hardening for context transport variants.

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
  - new `JSON` tab with last full context
  - last/average evaluation time fields
  - large OK/NOK counters
  - reset now resets all runtime counters and JSON snapshot

## Config Additions
- `pekat.oknok_source: context_result | result_field` (default `context_result`)

## Validation
- Automated tests passed: `9 passed`
- Added tests:
  - `tests/test_context_eval.py`
  - additional REST parser case in `tests/test_rest_url.py`

## Notes
- Branch: `v03`
- Stable tag is intentionally not created in this preview phase.
