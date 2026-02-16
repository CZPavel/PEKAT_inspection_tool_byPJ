# Changelog

All notable changes to this project are documented in this file.

## [3.4.0] - 2026-02-16

### Added
- New `Pekat Tuning` GUI tab with two sections:
  - Script Catalog for PEKAT Code module snippets and module assets
  - Library Installer panel with guided pyzbar install wizard
- New core module `pektool/core/tuning_catalog.py`:
  - script import from source folder
  - UTF-8 normalization with cp1250/latin1 fallback
  - raw + canonical storage in `resources/code_modules`
  - catalog metadata management (`catalog.json`)
- New core module `pektool/core/library_installer.py`:
  - manifest-based install planning
  - target validation for `<PEKAT_ROOT>/server`
  - dry-run summary and install execution with optional backup
- Bundled resources:
  - base script repository under `resources/code_modules`
  - pyzbar payload + manifest under `resources/pekat_libs/pyzbar`
- New helper script:
  - `resources/pekat_libs/pyzbar/helpers/add_libs_to_sys_path.py`
- New tests:
  - `tests/test_tuning_catalog.py`
  - `tests/test_library_installer.py`
  - `tests/test_gui_tuning.py` (Qt opt-in)

### Changed
- GUI title updated to `PEKAT Inspection Tool V03.4`.
- Main tab order now includes `Pekat Tuning` between JSON and Pekat Info.
- PyInstaller spec now bundles `resources/` into onedir build output.

### Documentation
- Updated `README.md` with v3.4 tuning features.
- Updated `docs/USER_GUIDE.md` with Pekat Tuning user workflow.
- Updated `docs/TECHNICAL_OVERVIEW.md` with new catalog/installer architecture.
- Added `docs/NEXT_STEPS.md` with follow-up items (user test, script descriptions, sound camera idea).

## [3.3.0] - 2026-02-16

### Added
- New `Pekat Info` GUI tab with:
  - common PEKAT port table (7000, 7002, 8000, 8000-8100, 1947)
  - clickable links for PM project list, PM UI, API test page, project root, and licensing/update page
  - common-port status check and range scan (8000-8100)
  - process-level ownership hints (`PEKAT PM HTTP`, `PEKAT PM TCP`, `PEKAT project`, `Other`, etc.)
- New core diagnostics module `pektool/core/port_info.py`.
- New tests:
  - `tests/test_port_info.py`
  - `tests/test_gui_pekat_info.py` (Qt opt-in)

### Changed
- GUI title updated to `PEKAT Inspection Tool V03.3`.
- Network section in `Pekat Info` now shows adapter cards side by side.
- Network cards are sorted so Wi-Fi and Bluetooth adapters are listed last.
- Network info focuses on adapter-level fields:
  - adapter name
  - network/profile name (if available)
  - MAC address
  - IPv4 + subnet mask

### Documentation
- Updated `README.md` for v3.3 scope.
- Updated `docs/USER_GUIDE.md` for Pekat Info behavior and adapter card layout.
- Updated `docs/TECHNICAL_OVERVIEW.md` with port diagnostics and network adapter rendering logic.
