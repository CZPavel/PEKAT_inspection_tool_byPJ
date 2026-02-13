import os
from pathlib import Path

import pytest

if os.environ.get("PEKTOOL_QT_TESTS") != "1":
    pytest.skip("Qt GUI tests are opt-in via PEKTOOL_QT_TESTS=1", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pektool.gui.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app
    app.closeAllWindows()
    app.quit()


def test_gui_file_actions_disabled_in_loop(qapp):
    window = MainWindow()
    try:
        for idx in range(window.run_mode_combo.count()):
            if window.run_mode_combo.itemData(idx) == "loop":
                window.run_mode_combo.setCurrentIndex(idx)
                break
        window._update_file_actions_loop_state()
        assert window.file_actions_enable_check.isEnabled() is False
        assert "Loop" in window.file_actions_info_label.text()
    finally:
        window.close()


def test_gui_section_enablement_by_mode(qapp):
    window = MainWindow()
    try:
        for idx in range(window.run_mode_combo.count()):
            if window.run_mode_combo.itemData(idx) == "initial_then_watch":
                window.run_mode_combo.setCurrentIndex(idx)
                break
        window.file_actions_enable_check.setChecked(True)

        for idx in range(window.file_actions_mode_combo.count()):
            if window.file_actions_mode_combo.itemData(idx) == "delete_after_eval":
                window.file_actions_mode_combo.setCurrentIndex(idx)
                break
        window._update_file_actions_mode_ui()
        assert window.file_ok_group.isEnabled() is False
        assert window.file_nok_group.isEnabled() is False

        for idx in range(window.file_actions_mode_combo.count()):
            if window.file_actions_mode_combo.itemData(idx) == "move_ok_delete_nok":
                window.file_actions_mode_combo.setCurrentIndex(idx)
                break
        window._update_file_actions_mode_ui()
        assert window.file_ok_group.isEnabled() is True
        assert window.file_nok_group.isEnabled() is False
    finally:
        window.close()


def test_gui_persist_file_action_settings(qapp, tmp_path, monkeypatch):
    cfg_path = tmp_path / "gui.yaml"
    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))

    window = MainWindow()
    try:
        window.file_actions_enable_check.setChecked(True)
        for idx in range(window.file_actions_mode_combo.count()):
            if window.file_actions_mode_combo.itemData(idx) == "move_by_result":
                window.file_actions_mode_combo.setCurrentIndex(idx)
                break
        window.file_ok_dir_edit.setText("C:/ok")
        window.file_nok_dir_edit.setText("C:/nok")
        window.file_ok_result_check.setChecked(True)
        window.file_nok_timestamp_check.setChecked(True)
        window.file_ok_string_check.setChecked(True)
        window.file_ok_string_edit.setText("batch")
        window._save_gui_settings()
    finally:
        window.close()

    loaded = MainWindow()
    try:
        assert loaded.file_actions_enable_check.isChecked() is True
        assert loaded.file_actions_mode_combo.currentData() == "move_by_result"
        assert loaded.file_ok_dir_edit.text() == "C:/ok"
        assert loaded.file_nok_dir_edit.text() == "C:/nok"
        assert loaded.file_ok_result_check.isChecked() is True
        assert loaded.file_nok_timestamp_check.isChecked() is True
        assert loaded.file_ok_string_check.isChecked() is True
        assert loaded.file_ok_string_edit.text() == "batch"
    finally:
        loaded.close()
