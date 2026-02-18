import os
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


def test_script_table_uses_xlsx_like_columns(qapp):
    tab = PekatTuningTab()
    try:
        headers = [tab.script_table.horizontalHeaderItem(i).text() for i in range(tab.script_table.columnCount())]
        assert headers == [
            "Soubor",
            "Kategorie",
            "K cemu slouzi",
            "Co dela",
            "Klicove context",
            "Zavislosti",
        ]
    finally:
        tab.close()


def test_copy_as_text_pushes_to_clipboard(monkeypatch, qapp):
    tab = PekatTuningTab()
    try:
        class DummyCatalog:
            def __init__(self):
                self.root = Path(".")

            def available_categories(self):
                return ["Flow control"]

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
                        category="Flow control",
                        tags=["Flow control"],
                        short_description="desc",
                        encoding_source="utf-8",
                        size_bytes=1,
                        sha256="x",
                        created_at="now",
                        updated_at="now",
                        empty=False,
                        purpose="purpose",
                        what_it_does="does",
                        context_keys="result",
                        dependencies="-",
                        description_source="generated",
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


def test_replace_action_uses_default_source_and_updates_status(monkeypatch, qapp, tmp_path):
    source_dir = tmp_path / "SCRIPTY_PEKAT_CODE"
    source_dir.mkdir()
    (source_dir / "A.txt").write_text("print('x')", encoding="utf-8")

    tab = PekatTuningTab()
    try:
        class DummyCatalog:
            def __init__(self):
                self.root = Path(".")
                self.called_source = None
                self.called_skip_empty = None

            def available_categories(self):
                return ["Flow control"]

            def list_assets(self, search="", category="all"):
                return []

            def replace_from_folder(self, source, skip_empty=True):
                self.called_source = source
                self.called_skip_empty = skip_empty
                from pektool.types import ScriptCatalogIndex

                return ScriptCatalogIndex(schema_version="1.0", generated_at="now", items=[]), 7, 1

            def get_asset_text(self, _id):
                return ""

            def export_asset(self, _id, destination):
                return destination

        dummy = DummyCatalog()
        tab.catalog = dummy
        monkeypatch.setattr("pektool.gui.tuning_widgets.DEFAULT_BASE_SCRIPTS_DIR", source_dir)
        tab._import_base_scripts()
        assert dummy.called_source == source_dir
        assert dummy.called_skip_empty is True
        assert "importovano 7" in tab.install_status_label.text()
        assert "preskoceno prazdnych 1" in tab.install_status_label.text()
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
