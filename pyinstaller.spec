# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

pyside6 = collect_all("PySide6")

hiddenimports = pyside6[2]
datas = pyside6[0]
binaries = pyside6[1]


cli_analysis = Analysis(
    ["entry_cli.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
cli_pyz = PYZ(cli_analysis.pure, cli_analysis.zipped_data, cipher=block_cipher)
cli_exe = EXE(
    cli_pyz,
    cli_analysis.scripts,
    cli_analysis.binaries,
    cli_analysis.zipfiles,
    cli_analysis.datas,
    name="pektool",
    console=True,
    exclude_binaries=True,
)


gui_analysis = Analysis(
    ["entry_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
gui_pyz = PYZ(gui_analysis.pure, gui_analysis.zipped_data, cipher=block_cipher)
gui_exe = EXE(
    gui_pyz,
    gui_analysis.scripts,
    gui_analysis.binaries,
    gui_analysis.zipfiles,
    gui_analysis.datas,
    name="pektool-gui",
    console=False,
    exclude_binaries=True,
)

coll = COLLECT(
    cli_exe,
    gui_exe,
    cli_analysis.binaries,
    cli_analysis.zipfiles,
    cli_analysis.datas,
    gui_analysis.binaries,
    gui_analysis.zipfiles,
    gui_analysis.datas,
    name="PEKAT_Inspection_tool_by_PJ",
)

