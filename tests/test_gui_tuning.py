import os
import time
from pathlib import Path

import pytest

if os.environ.get("PEKTOOL_QT_TESTS") != "1":
    pytest.skip("Qt GUI tests are opt-in via PEKTOOL_QT_TESTS=1", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pektool.gui.main import MainWindow
from pektool.gui.tuning_widgets import PekatTuningTab


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app
    app.closeAllWindows()
    app.quit()


def test_pekat_tuning_tab_exists(qapp):
    window = MainWindow()
    try:
        names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Pekat Tuning" in names
    finally:
        window.close()


def test_copy_as_text_pushes_to_clipboard(monkeypatch, qapp):
    tab = PekatTuningTab()
    try:
        class DummyCatalog:
            def __init__(self):
                self.root = Path(".")

            def available_categories(self):
                return ["general"]

            def list_assets(self, search="", category="all"):
                from pektool.types import ScriptAsset

                return [
                    ScriptAsset(
                        id="a1",
                        name="A",
                        source_filename="A.txt",
                        storage_path_utf8="",
                        storage_path_raw="",
                        format="txt",
                        category="general",
                        tags=["general"],
                        short_description="desc",
                        encoding_source="utf-8",
                        size_bytes=1,
                        sha256="x",
                        created_at="now",
                        updated_at="now",
                        empty=False,
                    )
                ]

            def get_asset_text(self, _id):
                return "copied-text"

            def export_asset(self, _id, destination):
                return destination

        tab.catalog = DummyCatalog()
        tab._refresh_catalog()
        tab._copy_selected_text()
        assert QtWidgets.QApplication.clipboard().text() == "copied-text"
    finally:
        tab.close()


def test_placeholder_buttons_disabled(qapp):
    tab = PekatTuningTab()
    try:
        assert tab.install_placeholder_2_btn.isEnabled() is False
        assert tab.install_placeholder_3_btn.isEnabled() is False
        assert tab.install_placeholder_4_btn.isEnabled() is False
    finally:
        tab.close()
