# Library Installer - pyzbar (v3.4)

This document describes the pyzbar installer flow used in `Pekat Tuning`.

## Resource locations

- Manifest:
  - `resources/pekat_libs/pyzbar/install_manifest.json`
- Payload:
  - `resources/pekat_libs/pyzbar/payload/...`
- Helper:
  - `resources/pekat_libs/pyzbar/helpers/add_libs_to_sys_path.py`

## Wizard flow

1. Intro + warning
2. Select PEKAT root path
3. Pre-check
   - target validation
   - write access check
   - running process hint
4. Dry-run summary
   - files to copy
   - new vs overwrite count
   - total size
5. Execute
   - optional backup before overwrite
   - copy results + error list

## Target path rule

Installer expects:
- `<PEKAT_ROOT>/server`

Payload is copied under this target according to manifest item mapping.

## Backups

When backup is enabled:
- `logs/installer/installer_backups/<library>_<timestamp>/...`

