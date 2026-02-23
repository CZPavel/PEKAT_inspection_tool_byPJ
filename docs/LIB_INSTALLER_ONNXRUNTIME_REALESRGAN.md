# Library Installer - ONNX Runtime + Real-ESRGAN

This document describes the fallback wizard flow for offline copy of ONNX Runtime + model
into PEKAT server path.

## Resource locations
- Manifest:
  - `resources/pekat_libs/onnxruntime_realesrgan/install_manifest.json`
- Payload:
  - `resources/pekat_libs/onnxruntime_realesrgan/payload/...`
- Helpers:
  - `resources/pekat_libs/onnxruntime_realesrgan/helpers/add_pydeps_to_sys_path.py`
  - `resources/pekat_libs/onnxruntime_realesrgan/helpers/code_module_onnx_realesrgan_cpu_smoke.py`
  - `resources/pekat_libs/onnxruntime_realesrgan/helpers/build_offline_payload.ps1`

## Wizard flow
1. Intro + warning (recommends variant A outside Program Files)
2. Select PEKAT root
3. Pre-check
   - target validation
   - write access check
   - payload completeness check
   - running process hint
4. Dry-run summary
5. Execute copy with optional backup

## Target path rule
- `<PEKAT_ROOT>/server`

## Backups
- `logs/installer/installer_backups/<library>_<timestamp>/...`

## Build payload
Use `helpers/build_offline_payload.ps1` to refresh model/runtime artifacts.

## Important note
Preferred production deployment is still `C:\ProgramData\PEKAT\pydeps`
loaded via `sys.path` in Code module. This installer is fallback for direct
server-copy environments.
