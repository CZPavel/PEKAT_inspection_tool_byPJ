# Dependency Links (v3.6)

Tento dokument popisuje hlavní návaznosti modulů, runtime tok dat a build vazby.

## Runtime architektura

`GUI/CLI -> Config -> Runner -> Clients`

1. `pektool/gui/main.py` a `pektool/cli.py` skládají `AppConfig`.
2. `pektool/config.py` drží validaci a migrace konfiguračních klíčů.
3. `pektool/core/runner.py` zajišťuje queue, dispatch, analyzaci a artefakty.
4. `pektool/clients/rest_client.py` a `pektool/clients/sdk_client.py` řeší přenos do PEKAT.

## Sound camera návaznost

`GUI Sound camera -> core/sound_camera/* -> Runner preview callback`

1. GUI karta `Sound camera` vytváří runtime audio config.
2. `pektool/core/sound_camera/engine.py` čte audio zdroj a renderuje snímky:
   - `render_payload.py`
   - `render_lissajous.py`
   - `render_classic.py`
   - `render_fuse7.py`
3. `Runner` přijímá frame tasky (`save_send` nebo `send_only`) a odesílá je klientům.
4. Preview callback streamuje poslední renderovaný frame zpět do GUI dialogu.

## Build návaznost (PyInstaller)

`pyinstaller.spec -> entry_gui.py / entry_cli.py -> dist`

1. `entry_gui.py` startuje `pektool.gui.main:main`.
2. `entry_cli.py` startuje `pektool.cli:app`.
3. `pyinstaller.spec` definuje hidden imports, data resources, icon a výstup.
4. Build skript `scripts/build_pyinstaller.ps1` spouští clean build.
5. Release artefakty vznikají v:
   - `dist/PEKAT_Inspection_tool_by_PJ_V03_6/pektool-gui.exe`
   - `dist/PEKAT_Inspection_tool_by_PJ_V03_6/pektool.exe`

## Dokumentační návaznosti

1. Uživatelský postup: `docs/USER_GUIDE.md`
2. Technická architektura: `docs/TECHNICAL_OVERVIEW.md`
3. Sound camera parametry: `docs/SOUND_CAMERA.md`
4. Release souhrn: `docs/RELEASE_3_6.md`
