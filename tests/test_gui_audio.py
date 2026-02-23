import os
import time
from pathlib import Path

import numpy as np
import pytest

if os.environ.get("PEKTOOL_QT_TESTS") != "1":
    pytest.skip("Qt GUI tests are opt-in via PEKTOOL_QT_TESTS=1", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pektool.core.sound_camera.models import SoundCameraFrame
from pektool.gui import main as gui_main
from pektool.gui.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app
    app.closeAllWindows()
    app.quit()


class _ConnectedStub:
    def __init__(self) -> None:
        import logging

        self.logger = logging.getLogger("gui-sound-test")

    def is_connected(self) -> bool:
        return True


class _RunningPreviewStub:
    def __init__(self) -> None:
        self.calls = []

    def is_running(self) -> bool:
        return True

    def reconfigure(self, config) -> None:
        self.calls.append(config)

    def stop(self) -> None:
        pass

    def poll_latest(self):
        return None


def test_sound_camera_tab_exists(qapp):
    window = MainWindow()
    try:
        names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Sound camera" in names
    finally:
        window.close()


def test_sound_camera_tab_uses_scroll_root_and_compact_spacing(qapp):
    window = MainWindow()
    try:
        scroll_areas = window.audio_tab.findChildren(QtWidgets.QScrollArea)
        assert scroll_areas
        common_form = window.audio_enable_check.parentWidget().layout()
        assert isinstance(common_form, QtWidgets.QFormLayout)
        assert common_form.horizontalSpacing() == 10
        assert common_form.verticalSpacing() <= 4
    finally:
        window.close()


def test_compact_min_heights_for_main_controls(qapp):
    window = MainWindow()
    try:
        for btn in [window.connect_btn, window.disconnect_btn, window.start_btn, window.stop_btn]:
            assert 36 <= btn.minimumHeight() <= 38
        assert 58 <= window.nok_count_value.minimumHeight() <= 60
        assert 58 <= window.ok_count_value.minimumHeight() <= 60
    finally:
        window.close()


def test_gui_persist_sound_settings(qapp, tmp_path, monkeypatch):
    cfg_path = tmp_path / "gui_sound.yaml"
    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))

    window = MainWindow()
    try:
        window.audio_enable_check.setChecked(True)
        window.audio_approach_combo.setCurrentIndex(1)  # lissajous
        window.audio_source_combo.setCurrentIndex(2)  # sine
        window.audio_send_mode_combo.setCurrentIndex(1)  # send_only
        window.audio_sine_freq_spin.setValue(523.2)
        window.audio_file_prefix_edit.setText("custom_sound")
        window.audio_snapshot_dir_edit.setText("C:/sound-snapshots")
        window.audio_fps_spin.setValue(0.25)
        window.payload_overlay_grid_check.setChecked(False)
        window.payload_overlay_legend_check.setChecked(False)
        window.payload_variant_combo.setCurrentText("invert_all")
        window._save_gui_settings()
    finally:
        window.close()

    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))
    loaded = MainWindow()
    try:
        assert loaded.audio_enable_check.isChecked() is True
        assert str(loaded.audio_approach_combo.currentData()) == "lissajous"
        assert str(loaded.audio_source_combo.currentData()) == "sine"
        assert str(loaded.audio_send_mode_combo.currentData()) == "send_only"
        assert loaded.audio_sine_freq_spin.value() == pytest.approx(523.2, abs=0.1)
        assert loaded.audio_file_prefix_edit.text() == "custom_sound"
        assert loaded.audio_fps_spin.value() == pytest.approx(0.25, abs=1e-3)
        assert loaded.payload_overlay_grid_check.isChecked() is False
        assert loaded.payload_overlay_legend_check.isChecked() is False
    finally:
        loaded.close()


def test_gui_loads_legacy_interval_as_fps(qapp, tmp_path, monkeypatch):
    cfg_path = tmp_path / "gui_sound_legacy.yaml"
    cfg_path.write_text("sound_interval_sec: 2.0\n", encoding="utf-8")
    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))
    window = MainWindow()
    try:
        assert window.audio_fps_spin.value() == pytest.approx(0.5, abs=1e-3)
    finally:
        window.close()


def test_gui_persist_classic_advanced_settings(qapp, tmp_path, monkeypatch):
    cfg_path = tmp_path / "gui_sound_classic.yaml"
    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))

    window = MainWindow()
    try:
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        window._set_combo_data(window.classic_style_combo, "fuse7")
        window._set_combo_data(window.classic_axis_combo, "mel")
        window.classic_n_fft_spin.setValue(8192)
        window.classic_win_ms_spin.setValue(40.0)
        window.classic_hop_ms_spin.setValue(0.5)
        window.classic_top_db_spin.setValue(75.0)
        window.classic_fmax_spin.setValue(18000.0)
        window.classic_flux_gain_spin.setValue(222.0)
        window.classic_edge_gain_spin.setValue(111.0)
        window.classic_norm_p_spin.setValue(97.5)
        window.classic_p_lo_spin.setValue(2.0)
        window.classic_p_hi_spin.setValue(98.0)
        window._save_gui_settings()
    finally:
        window.close()

    monkeypatch.setattr(MainWindow, "_gui_config_path", lambda self: Path(cfg_path))
    loaded = MainWindow()
    try:
        assert str(loaded.classic_style_combo.currentData()) == "fuse7"
        assert str(loaded.classic_axis_combo.currentData()) == "mel"
        assert loaded.classic_n_fft_spin.value() == 8192
        assert loaded.classic_win_ms_spin.value() == pytest.approx(40.0, abs=1e-6)
        assert loaded.classic_hop_ms_spin.value() == pytest.approx(0.5, abs=1e-6)
        assert loaded.classic_top_db_spin.value() == pytest.approx(75.0, abs=1e-6)
        assert loaded.classic_fmax_spin.value() == pytest.approx(18000.0, abs=1e-6)
        assert loaded.classic_flux_gain_spin.value() == pytest.approx(222.0, abs=1e-6)
        assert loaded.classic_edge_gain_spin.value() == pytest.approx(111.0, abs=1e-6)
        assert loaded.classic_norm_p_spin.value() == pytest.approx(97.5, abs=1e-6)
        assert loaded.classic_p_lo_spin.value() == pytest.approx(2.0, abs=1e-6)
        assert loaded.classic_p_hi_spin.value() == pytest.approx(98.0, abs=1e-6)
    finally:
        loaded.close()


def test_sound_save_send_requires_valid_snapshot_dir(qapp, tmp_path, monkeypatch):
    warning_calls = []

    def _warning(*args, **kwargs):
        warning_calls.append((args, kwargs))
        return QtWidgets.QMessageBox.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", _warning)
    blocked = tmp_path / "not_a_dir.txt"
    blocked.write_text("x", encoding="utf-8")

    window = MainWindow()
    try:
        window.state.connection = _ConnectedStub()
        window.audio_enable_check.setChecked(True)
        window.audio_send_mode_combo.setCurrentIndex(0)  # save_send
        window.audio_snapshot_dir_edit.setText(str(blocked))
        window._start()
        assert warning_calls
        assert window.state.runner is None
    finally:
        window.close()


def test_sound_send_only_disables_source_file_actions_toggle(qapp):
    window = MainWindow()
    try:
        window.audio_enable_check.setChecked(True)
        window.audio_send_mode_combo.setCurrentIndex(1)  # send_only
        window._update_sound_send_mode_ui()
        assert window.file_actions_enable_check.isEnabled() is False
    finally:
        window.close()


def test_preview_popup_updates_frame(qapp):
    window = MainWindow()
    try:
        window._open_sound_preview_dialog()
        frame = SoundCameraFrame(
            image_bgr=np.zeros((80, 120, 3), dtype=np.uint8),
            timestamp=0.0,
            label_stem="x",
            source="sine",
            approach="payload",
            meta={"width_px": 120, "height_px": 80},
        )
        window._on_runner_sound_preview_frame(frame)
        window._poll_sound_preview_sources()
        dialog = window._ensure_sound_preview_dialog()
        assert dialog.latest_image().shape == (80, 120, 3)
        dialog.hide()
    finally:
        window.close()


def test_preview_auto_reconfigure_on_approach_change(qapp):
    window = MainWindow()
    try:
        stub = _RunningPreviewStub()
        window.sound_preview_controller = stub
        window.audio_approach_combo.setCurrentIndex(1)  # lissajous
        deadline = time.time() + 1.0
        while time.time() < deadline and not stub.calls:
            qapp.processEvents()
            time.sleep(0.05)
        assert stub.calls
        assert stub.calls[-1].audio.approach == "lissajous"
    finally:
        window.close()


def test_preview_auto_reconfigure_on_classic_style_change(qapp):
    window = MainWindow()
    try:
        stub = _RunningPreviewStub()
        window.sound_preview_controller = stub
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        window._set_combo_data(window.classic_style_combo, "fuse7")
        deadline = time.time() + 1.0
        while time.time() < deadline and not stub.calls:
            qapp.processEvents()
            time.sleep(0.05)
        assert stub.calls
        assert stub.calls[-1].audio.classic.style == "fuse7"
    finally:
        window.close()


def test_classic_layout_uses_advanced_settings_dialog(qapp):
    window = MainWindow()
    try:
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        page = window.audio_settings_stack.widget(2)
        groups = [g.title() for g in page.findChildren(QtWidgets.QGroupBox)]
        assert "Základní nastavení" in groups
        assert "Pokročilé nastavení" not in groups
        assert window.classic_advanced_btn.text().startswith("Pokročilé")
        window._open_classic_advanced_dialog()
        dialog = window._ensure_classic_advanced_dialog()
        assert dialog.isVisible() is True
        dialog_groups = [g.title() for g in dialog.findChildren(QtWidgets.QGroupBox)]
        assert "Pokročilé nastavení" in dialog_groups
        styles = [window.classic_style_combo.itemData(i) for i in range(window.classic_style_combo.count())]
        axes = [window.classic_axis_combo.itemData(i) for i in range(window.classic_axis_combo.count())]
        assert styles == ["classic", "fuse7", "fuse4_base"]
        assert axes == ["linear", "log", "mel"]
    finally:
        window.close()


def test_classic_axis_is_disabled_for_fuse_styles(qapp):
    window = MainWindow()
    try:
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        window._set_combo_data(window.classic_style_combo, "fuse7")
        window._update_classic_style_ui()
        assert window.classic_axis_combo.isEnabled() is False
        window._set_combo_data(window.classic_style_combo, "classic")
        window._update_classic_style_ui()
        assert window.classic_axis_combo.isEnabled() is True
    finally:
        window.close()


def test_sound_formula_labels_update(qapp):
    window = MainWindow()
    try:
        window.audio_window_spin.setValue(2.0)
        window.audio_fps_spin.setValue(0.25)
        window.payload_frame_seconds_spin.setValue(1.0)
        window.payload_overlap_combo.setCurrentIndex(4)  # 50%
        window._update_sound_formula_labels()
        assert "interval = 1/FPS = 4.000s" in window.audio_fps_info_label.text()
        assert "required_samples=" in window.payload_formula_label.text()
        assert "covered_audio_sec=" in window.payload_formula_label.text()
        window.audio_fps_spin.setValue(1.0)
        window._update_sound_formula_labels()
        assert "Overlap 1.000 s (50.0 %)" in window.classic_overlap_info_label.text()
        window.audio_fps_spin.setValue(0.25)
        window._update_sound_formula_labels()
        assert "Gap 2.000 s" in window.classic_overlap_info_label.text()
    finally:
        window.close()


def test_start_preview_blocks_classic_when_scipy_missing(qapp, monkeypatch):
    warning_calls = []

    def _warning(*args, **kwargs):
        warning_calls.append((args, kwargs))
        return QtWidgets.QMessageBox.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", _warning)
    monkeypatch.setattr(gui_main, "classic_dependencies_status", lambda: {"scipy_available": False, "error": "x"})
    window = MainWindow()
    try:
        window.audio_enable_check.setChecked(True)
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        window._start_sound_preview()
        assert warning_calls
        assert "chybí scipy" in window.audio_device_status_label.text().lower()
        assert window.sound_preview_controller is None
    finally:
        window.close()


def test_start_sending_blocks_classic_when_scipy_missing(qapp, monkeypatch):
    warning_calls = []

    def _warning(*args, **kwargs):
        warning_calls.append((args, kwargs))
        return QtWidgets.QMessageBox.Ok

    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", _warning)
    monkeypatch.setattr(gui_main, "classic_dependencies_status", lambda: {"scipy_available": False, "error": "x"})
    window = MainWindow()
    try:
        window.state.connection = _ConnectedStub()
        window.audio_enable_check.setChecked(True)
        window.audio_approach_combo.setCurrentIndex(2)  # classic
        window.audio_send_mode_combo.setCurrentIndex(1)  # send_only
        window._start()
        assert warning_calls
        assert window.state.runner is None
        assert "chybí scipy" in window.audio_device_status_label.text().lower()
    finally:
        window.close()
