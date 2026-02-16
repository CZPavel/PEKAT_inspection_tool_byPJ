# Changelog

All notable changes to this project are documented in this file.

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

