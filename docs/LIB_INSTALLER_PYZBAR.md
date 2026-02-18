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

Wizard keeps the same visual style as the main application and does not add extra popup flows outside the guided steps.

## Target path rule

Installer expects:
- `<PEKAT_ROOT>/server`

Payload is copied under this target according to manifest item mapping.

Default path behavior:
- Searches `C:\Program Files` for `PEKAT VISION x.y.z`
- Uses numeric semantic ordering (`x`, `y`, `z`) to select the newest installed version
- Falls back to `C:\Program Files\PEKAT VISION` if no versioned folder is found

## Backups

When backup is enabled:
- `logs/installer/installer_backups/<library>_<timestamp>/...`

## Offline payload checks

- Installer validates that every manifest `source` path exists under local `payload`.
- Pre-check reports missing payload files before execute phase.
- Current offline payload includes pyzbar runtime files, including `libzbar-64.dll`.
