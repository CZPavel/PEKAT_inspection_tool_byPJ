from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np
import yaml
from PySide6 import QtCore, QtGui, QtWidgets

from ..config import AppConfig
from ..core.connection import ConnectionManager
from ..core.port_info import (
    KnownPortEntry,
    NetworkAdapterInfo,
    PortScanResult,
    check_ports,
    get_network_adapters_info,
    get_known_pekat_ports,
    scan_port_range,
)
from ..core.runner import Runner
from ..core.sound_camera.audio_sources import list_loopback_devices, list_microphone_devices
from ..core.sound_camera.models import SoundCameraFrame
from ..core.sound_camera.preview_controller import SoundCameraPreviewController
from ..core.sound_camera.render_classic import classic_dependencies_status
from ..logging_setup import setup_logging
from .sound_camera_preview import SoundCameraPreviewDialog
from .state import GuiState
from .tuning_widgets import PekatTuningTab
from .widgets import LogEmitter, QtLogHandler


class MainWindow(QtWidgets.QMainWindow):
    """Main GUI window for configuration, control and live feedback."""

    ui_callback_signal = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PEKAT Inspection Tool V03.6")
        self.resize(980, 640)

        self.state = GuiState()
        self.selected_files: List[str] = []
        self.stop_requested = False
        self.stop_start_time: float | None = None
        self.last_ping_time = 0.0
        self.health_check_inflight = False
        self.port_scan_running = False
        self.network_info_loading = False
        self.known_port_entries: List[KnownPortEntry] = []
        self.known_port_row_map: Dict[str, List[int]] = {}
        self.sound_preview_controller: SoundCameraPreviewController | None = None
        self.sound_preview_dialog: SoundCameraPreviewDialog | None = None
        self.sound_preview_queue: "queue.Queue[SoundCameraFrame]" = queue.Queue(maxsize=8)
        self.classic_advanced_dialog: QtWidgets.QDialog | None = None
        self._scroll_tab_content: Dict[QtWidgets.QWidget, QtWidgets.QWidget] = {}

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = QtWidgets.QWidget()
        self.file_actions_tab = QtWidgets.QWidget()
        self.json_tab = QtWidgets.QWidget()
        self.tuning_tab = PekatTuningTab()
        self.audio_tab = QtWidgets.QWidget()
        self.pekat_info_tab = QtWidgets.QWidget()
        self.log_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.config_tab, "Konfigurace")
        self.tabs.addTab(self.file_actions_tab, "Manipulace se soubory")
        self.tabs.addTab(self.json_tab, "Last Context JSON")
        self.tabs.addTab(self.tuning_tab, "Pekat Tuning")
        self.tabs.addTab(self.audio_tab, "Sound camera")
        self.tabs.addTab(self.pekat_info_tab, "Pekat Info")
        self.tabs.addTab(self.log_tab, "Log")

        self._build_config_tab()
        self._build_file_actions_tab()
        self._build_json_tab()
        self._build_audio_tab()
        self._build_pekat_info_tab()
        self._build_log_tab()

        self.emitter = LogEmitter()
        self.emitter.message.connect(self._append_log)
        self.qt_handler = QtLogHandler(self.emitter)
        self.qt_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_status)
        self.ui_callback_signal.connect(lambda callback: callback())
        self.tabs.currentChanged.connect(self._on_tab_changed)

        self.sound_preview_timer = QtCore.QTimer(self)
        self.sound_preview_timer.setInterval(100)
        self.sound_preview_timer.timeout.connect(self._poll_sound_preview_sources)
        self.sound_preview_timer.start()
        self.sound_preview_reconfig_timer = QtCore.QTimer(self)
        self.sound_preview_reconfig_timer.setSingleShot(True)
        self.sound_preview_reconfig_timer.setInterval(250)
        self.sound_preview_reconfig_timer.timeout.connect(self._reconfigure_sound_preview_from_gui)

        self._load_gui_settings()
        QtCore.QTimer.singleShot(0, self._apply_adaptive_window_size)

    @staticmethod
    def _apply_compact_form_layout(form: QtWidgets.QFormLayout) -> None:
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

    @staticmethod
    def _apply_compact_box_layout(layout: QtWidgets.QLayout) -> None:
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

    def _build_scroll_tab_root(
        self, tab: QtWidgets.QWidget
    ) -> Tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        root = QtWidgets.QVBoxLayout(tab)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        scroll = QtWidgets.QScrollArea(tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        root.addWidget(scroll)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        self._apply_compact_box_layout(content_layout)
        scroll.setWidget(content)
        self._scroll_tab_content[tab] = content
        return content, content_layout

    def _apply_adaptive_window_size(self) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        screen = app.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry().size()
        base_hint = QtCore.QSize(980, 640)
        sound_hint = QtCore.QSize(0, 0)
        sound_content = self._scroll_tab_content.get(self.audio_tab)
        if sound_content is not None:
            sound_hint = sound_hint.expandedTo(sound_content.sizeHint())
        if hasattr(self, "audio_common_group"):
            sound_hint = sound_hint.expandedTo(self.audio_common_group.sizeHint())
        if hasattr(self, "audio_settings_stack"):
            sound_hint = sound_hint.expandedTo(self.audio_settings_stack.sizeHint())
            for idx in range(self.audio_settings_stack.count()):
                widget = self.audio_settings_stack.widget(idx)
                if widget is not None:
                    sound_hint = sound_hint.expandedTo(widget.sizeHint())
        if sound_hint.width() > 0 and sound_hint.height() > 0:
            base_hint = base_hint.expandedTo(
                QtCore.QSize(sound_hint.width() + 220, sound_hint.height() + 240)
            )
        for tab_index in range(self.tabs.count()):
            tab_widget = self.tabs.widget(tab_index)
            if tab_widget is None:
                continue
            if tab_widget.findChild(QtWidgets.QScrollArea) is not None:
                continue
            base_hint = base_hint.expandedTo(tab_widget.sizeHint())
        base_hint = base_hint.expandedTo(self.tabs.sizeHint())
        desired = QtCore.QSize(base_hint.width() + 120, base_hint.height() + 130)

        max_w = max(640, int(available.width() * 0.96))
        max_h = max(480, int(available.height() * 0.93))
        min_w = 980
        min_h = 640

        target_w = min(max(min_w, desired.width()), max_w)
        target_h = min(max(min_h, desired.height()), max_h)
        if max_w < min_w:
            target_w = max_w
        if max_h < min_h:
            target_h = max_h
        self.resize(target_w, target_h)

    def _build_config_tab(self) -> None:
        _, content_layout = self._build_scroll_tab_root(self.config_tab)
        layout = QtWidgets.QFormLayout()
        self._apply_compact_form_layout(layout)
        content_layout.addLayout(layout)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["sdk", "rest"])
        self.mode_combo.setCurrentText("rest")

        self.host_edit = QtWidgets.QLineEdit("127.0.0.1")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8000)

        self.project_path_edit = QtWidgets.QLineEdit("")

        self.folder_edit = QtWidgets.QLineEdit("")
        browse_btn = QtWidgets.QPushButton("Vybrat složku")
        browse_btn.clicked.connect(self._select_folder)

        folder_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(folder_layout)
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_btn)

        self.include_subfolders_check = QtWidgets.QCheckBox("Zahrnout podsložky")
        self.include_subfolders_check.setChecked(True)

        self.file_select_btn = QtWidgets.QPushButton("Vybrat soubory")
        self.file_select_btn.clicked.connect(self._select_files)
        self.files_label = QtWidgets.QLabel("0 souborů")

        files_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(files_layout)
        files_layout.addWidget(self.file_select_btn)
        files_layout.addWidget(self.files_label)

        self.run_mode_combo = QtWidgets.QComboBox()
        run_modes = [
            ("Loop (Nacita snimky k vyhodnoceni stale dokola)", "loop"),
            ("Once (Odesle postupne vsechny snimky k vyhodnoceni jen jednou)", "once"),
            (
                "Send ALL Once and Watch (Odesle vsechny snimky jednou a pak ceka na dalsi)",
                "initial_then_watch",
            ),
            (
                "Just Watch (Ignoruje stavajici snimky a ceka jen na nove)",
                "just_watch",
            ),
        ]
        for index, (label, value) in enumerate(run_modes):
            self.run_mode_combo.addItem(label, value)
            self.run_mode_combo.setItemData(index, label, QtCore.Qt.ToolTipRole)
        self._set_run_mode_combo("initial_then_watch")
        self.run_mode_combo.currentIndexChanged.connect(self._update_file_actions_loop_state)

        self.delay_spin = QtWidgets.QSpinBox()
        self.delay_spin.setRange(0, 600000)
        self.delay_spin.setValue(150)

        self.data_filename_check = QtWidgets.QCheckBox("Include filename")
        self.data_filename_check.setChecked(True)
        self.data_timestamp_check = QtWidgets.QCheckBox("Include timestamp")
        self.data_string_check = QtWidgets.QCheckBox("Include string")
        self.data_string_edit = QtWidgets.QLineEdit("")
        self.data_string_edit.setEnabled(False)
        self.data_string_check.toggled.connect(self.data_string_edit.setEnabled)

        self.api_key_value = ""
        self.api_key_location_value = "query"
        self.api_key_name_value = "api_key"
        self.api_key_button = QtWidgets.QPushButton("API key setup")
        self.api_key_button.clicked.connect(self._setup_api_key)

        layout.addRow("Režim (SDK/REST)", self.mode_combo)
        layout.addRow("Host", self.host_edit)
        layout.addRow("Port", self.port_spin)
        layout.addRow("Project path", self.project_path_edit)
        layout.addRow("Složka", folder_layout)
        layout.addRow("", self.include_subfolders_check)
        layout.addRow("Soubory", files_layout)
        layout.addRow("Režim běhu", self.run_mode_combo)
        layout.addRow("Prodleva (ms)", self.delay_spin)
        data_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(data_layout)
        data_layout.addWidget(self.data_filename_check)
        data_layout.addWidget(self.data_timestamp_check)
        data_layout.addWidget(self.data_string_check)
        data_layout.addWidget(self.data_string_edit)
        layout.addRow("Data", data_layout)
        layout.addRow("API key", self.api_key_button)

        self.pm_tcp_enabled_check = QtWidgets.QCheckBox("PM TCP enabled")
        self.pm_tcp_host_edit = QtWidgets.QLineEdit("127.0.0.1")
        self.pm_tcp_port_spin = QtWidgets.QSpinBox()
        self.pm_tcp_port_spin.setRange(1, 65535)
        self.pm_tcp_port_spin.setValue(7002)

        self.pm_policy_combo = QtWidgets.QComboBox()
        self.pm_policy_combo.addItem("Off (status only)", "off")
        self.pm_policy_combo.addItem("Auto-start on Connect", "auto_start")
        self.pm_policy_combo.addItem("Auto-start + Auto-stop on Disconnect", "auto_start_stop")
        self.pm_policy_combo.addItem("Automatic restart", "auto_restart")

        pm_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(pm_layout)
        pm_layout.addWidget(self.pm_tcp_enabled_check)
        pm_layout.addWidget(QtWidgets.QLabel("Host"))
        pm_layout.addWidget(self.pm_tcp_host_edit)
        pm_layout.addWidget(QtWidgets.QLabel("Port"))
        pm_layout.addWidget(self.pm_tcp_port_spin)
        pm_layout.addWidget(QtWidgets.QLabel("Policy"))
        pm_layout.addWidget(self.pm_policy_combo)
        layout.addRow("Project control", pm_layout)

        self.pm_note_label = QtWidgets.QLabel(
            "Funguje pouze pokud je TCP server v Projects Manageru aktivní."
        )
        layout.addRow("", self.pm_note_label)

        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.disconnect_btn = QtWidgets.QPushButton("Disconnect")
        self.start_btn = QtWidgets.QPushButton("Start sending")
        self.stop_btn = QtWidgets.QPushButton("Stop sending")
        self.disconnect_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

        for btn in [self.connect_btn, self.disconnect_btn, self.start_btn, self.stop_btn]:
            btn.setMinimumHeight(36)
            btn.setMinimumWidth(140)

        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        btn_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(btn_layout)
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.disconnect_btn)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)

        self.connection_label = QtWidgets.QLabel("Disconnected")
        self.send_status_label = QtWidgets.QLabel("stopped")
        self.production_label = QtWidgets.QLabel("Production Mode: Unknown")
        self.data_preview_label = QtWidgets.QLabel("")
        self.count_label = QtWidgets.QLabel("0")
        self.last_eval_time_label = QtWidgets.QLabel("-")
        self.avg_eval_time_label = QtWidgets.QLabel("-")
        self.reset_counter_btn = QtWidgets.QPushButton("Reset counter and list")
        self.reset_counter_btn.clicked.connect(self._reset_counters)
        self.nok_count_value = QtWidgets.QLabel("0")
        self.ok_count_value = QtWidgets.QLabel("0")
        self.nok_count_value.setAlignment(QtCore.Qt.AlignCenter)
        self.ok_count_value.setAlignment(QtCore.Qt.AlignCenter)
        self.nok_count_value.setMinimumHeight(58)
        self.ok_count_value.setMinimumHeight(58)
        self.nok_count_value.setStyleSheet(
            "font-size: 28px; font-weight: 700; border: 1px solid #444; background: #2b1b1b;"
        )
        self.ok_count_value.setStyleSheet(
            "font-size: 28px; font-weight: 700; border: 1px solid #444; background: #1f2f1f;"
        )

        layout.addRow(btn_layout)
        layout.addRow("Connection", self.connection_label)
        layout.addRow("Sending", self.send_status_label)
        layout.addRow("Production Mode", self.production_label)
        layout.addRow("Data preview", self.data_preview_label)
        count_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(count_layout)
        count_layout.addWidget(self.count_label)
        count_layout.addWidget(self.reset_counter_btn)
        layout.addRow("Odesláno", count_layout)
        layout.addRow("Posledni vyhodnoceni (ms)", self.last_eval_time_label)
        layout.addRow("Prumerny cas (ms)", self.avg_eval_time_label)

        ok_nok_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(ok_nok_layout)
        nok_box = QtWidgets.QGroupBox("NOK")
        ok_box = QtWidgets.QGroupBox("OK")
        nok_box_layout = QtWidgets.QVBoxLayout(nok_box)
        ok_box_layout = QtWidgets.QVBoxLayout(ok_box)
        self._apply_compact_box_layout(nok_box_layout)
        self._apply_compact_box_layout(ok_box_layout)
        nok_box_layout.addWidget(self.nok_count_value)
        ok_box_layout.addWidget(self.ok_count_value)
        ok_nok_layout.addWidget(nok_box)
        ok_nok_layout.addWidget(ok_box)
        layout.addRow("Vyhodnoceni", ok_nok_layout)
        content_layout.addStretch(1)

        self.pm_tcp_enabled_check.toggled.connect(self._update_pm_controls)
        self.project_path_edit.textChanged.connect(self._update_pm_controls)
        self._update_pm_controls()
        self._update_file_actions_loop_state()

    def _build_file_actions_tab(self) -> None:
        _, layout = self._build_scroll_tab_root(self.file_actions_tab)

        self.file_actions_enable_check = QtWidgets.QCheckBox("Povolit manipulaci se soubory")
        self.file_actions_save_json_check = QtWidgets.QCheckBox("Ukladat JSON Context")
        self.file_actions_save_processed_check = QtWidgets.QCheckBox("Save PROCESSED Image")
        self.file_actions_info_label = QtWidgets.QLabel("")
        self.file_actions_info_label.setStyleSheet("color: #777;")
        self.file_actions_processed_hint = QtWidgets.QLabel(
            "Processed image will be saved as ANOTATED_<original_name>.png by default."
        )
        self.file_actions_processed_hint.setStyleSheet("color: #777;")

        self.file_actions_mode_combo = QtWidgets.QComboBox()
        self.file_actions_mode_combo.addItem("Po vyhodnoceni mazat soubory", "delete_after_eval")
        self.file_actions_mode_combo.addItem("Presouvat podle vyhodnoceni", "move_by_result")
        self.file_actions_mode_combo.addItem("Presun kdyz OK - Smaz kdyz NOK", "move_ok_delete_nok")
        self.file_actions_mode_combo.addItem("Smaz kdyz OK - Presun kdyz NOK", "delete_ok_move_nok")

        top_checks = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(top_checks)
        top_checks.addWidget(self.file_actions_enable_check)
        top_checks.addWidget(self.file_actions_save_json_check)
        top_checks.addWidget(self.file_actions_save_processed_check)

        top_form = QtWidgets.QFormLayout()
        self._apply_compact_form_layout(top_form)
        top_form.addRow("", top_checks)
        top_form.addRow("Rezim manipulace", self.file_actions_mode_combo)
        top_form.addRow("", self.file_actions_processed_hint)
        top_form.addRow("", self.file_actions_info_label)
        layout.addLayout(top_form)
        self.file_actions_top_form = top_form

        self.file_ok_group = QtWidgets.QGroupBox("Sekce OK")
        ok_layout = QtWidgets.QFormLayout(self.file_ok_group)
        self._apply_compact_form_layout(ok_layout)
        self.file_ok_dir_edit = QtWidgets.QLineEdit("")
        self.file_ok_browse_btn = QtWidgets.QToolButton()
        self.file_ok_browse_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.file_ok_browse_btn.setToolTip("Vybrat cilovou slozku")
        self.file_ok_browse_btn.clicked.connect(lambda: self._select_target_dir(self.file_ok_dir_edit))
        ok_dir_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(ok_dir_layout)
        ok_dir_layout.addWidget(self.file_ok_dir_edit)
        ok_dir_layout.addWidget(self.file_ok_browse_btn)
        self.file_ok_daily_check = QtWidgets.QCheckBox("Vytvorit novou slozku pro kazdy den (YYYY_MM_DD)")
        self.file_ok_hourly_check = QtWidgets.QCheckBox("Vytvorit novou slozku pro kazdou hodinu (MM_DD_HH)")
        self.file_ok_result_check = QtWidgets.QCheckBox("Include RESULT")
        self.file_ok_timestamp_check = QtWidgets.QCheckBox("Include Timestamp")
        self.file_ok_string_check = QtWidgets.QCheckBox("Include String")
        self.file_ok_string_edit = QtWidgets.QLineEdit("")
        self.file_ok_string_edit.setEnabled(False)
        self.file_ok_string_check.toggled.connect(self._update_file_actions_string_edits)
        ok_layout.addRow("Cilova slozka", ok_dir_layout)
        ok_layout.addRow("", self.file_ok_daily_check)
        ok_layout.addRow("", self.file_ok_hourly_check)
        ok_layout.addRow("", self.file_ok_result_check)
        ok_layout.addRow("", self.file_ok_timestamp_check)
        ok_layout.addRow("", self.file_ok_string_check)
        ok_layout.addRow("Text", self.file_ok_string_edit)

        self.file_nok_group = QtWidgets.QGroupBox("Sekce NOK")
        nok_layout = QtWidgets.QFormLayout(self.file_nok_group)
        self._apply_compact_form_layout(nok_layout)
        self.file_nok_dir_edit = QtWidgets.QLineEdit("")
        self.file_nok_browse_btn = QtWidgets.QToolButton()
        self.file_nok_browse_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.file_nok_browse_btn.setToolTip("Vybrat cilovou slozku")
        self.file_nok_browse_btn.clicked.connect(lambda: self._select_target_dir(self.file_nok_dir_edit))
        nok_dir_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(nok_dir_layout)
        nok_dir_layout.addWidget(self.file_nok_dir_edit)
        nok_dir_layout.addWidget(self.file_nok_browse_btn)
        self.file_nok_daily_check = QtWidgets.QCheckBox("Vytvorit novou slozku pro kazdy den (YYYY_MM_DD)")
        self.file_nok_hourly_check = QtWidgets.QCheckBox("Vytvorit novou slozku pro kazdou hodinu (MM_DD_HH)")
        self.file_nok_result_check = QtWidgets.QCheckBox("Include RESULT")
        self.file_nok_timestamp_check = QtWidgets.QCheckBox("Include Timestamp")
        self.file_nok_string_check = QtWidgets.QCheckBox("Include String")
        self.file_nok_string_edit = QtWidgets.QLineEdit("")
        self.file_nok_string_edit.setEnabled(False)
        self.file_nok_string_check.toggled.connect(self._update_file_actions_string_edits)
        nok_layout.addRow("Cilova slozka", nok_dir_layout)
        nok_layout.addRow("", self.file_nok_daily_check)
        nok_layout.addRow("", self.file_nok_hourly_check)
        nok_layout.addRow("", self.file_nok_result_check)
        nok_layout.addRow("", self.file_nok_timestamp_check)
        nok_layout.addRow("", self.file_nok_string_check)
        nok_layout.addRow("Text", self.file_nok_string_edit)

        sections_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(sections_layout)
        sections_layout.addWidget(self.file_ok_group, 1)
        sections_layout.addWidget(self.file_nok_group, 1)
        self.file_actions_sections_layout = sections_layout
        layout.addLayout(sections_layout)
        layout.addStretch(1)

        self.file_actions_enable_check.toggled.connect(self._update_file_actions_mode_ui)
        self.file_actions_save_json_check.toggled.connect(self._update_file_actions_mode_ui)
        self.file_actions_save_processed_check.toggled.connect(self._update_file_actions_mode_ui)
        self.file_actions_mode_combo.currentIndexChanged.connect(self._update_file_actions_mode_ui)
        self._update_file_actions_mode_ui()

    def _select_target_dir(self, target_edit: QtWidgets.QLineEdit) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Vyberte cilovou slozku")
        if folder:
            target_edit.setText(folder)

    def _update_file_actions_loop_state(self) -> None:
        if not hasattr(self, "file_actions_enable_check"):
            return
        is_loop_mode = str(self.run_mode_combo.currentData() or "") == "loop"
        is_sound_enabled = hasattr(self, "audio_enable_check") and self.audio_enable_check.isChecked()
        send_mode = str(self.audio_send_mode_combo.currentData() or "save_send")
        send_only_sound = is_sound_enabled and send_mode == "send_only"
        if send_only_sound:
            self.file_actions_enable_check.blockSignals(True)
            self.file_actions_enable_check.setChecked(False)
            self.file_actions_enable_check.blockSignals(False)
            self.file_actions_enable_check.setEnabled(False)
            self.file_actions_info_label.setText(
                "V režimu Sound camera Send-only jsou zdrojové move/delete akce vypnuté."
            )
        elif is_loop_mode and not is_sound_enabled:
            self.file_actions_enable_check.blockSignals(True)
            self.file_actions_enable_check.setChecked(False)
            self.file_actions_enable_check.blockSignals(False)
            self.file_actions_enable_check.setEnabled(False)
            self.file_actions_info_label.setText(
                "V rezimu Loop neni dostupna manipulace se zdrojovymi soubory."
            )
        else:
            self.file_actions_enable_check.setEnabled(True)
            if is_loop_mode and is_sound_enabled:
                self.file_actions_info_label.setText(
                    "Loop omezení je vypnuto, protože je aktivní Sound camera."
                )
            else:
                self.file_actions_info_label.setText("")
        self._update_file_actions_mode_ui()

    def _update_file_actions_string_edits(self) -> None:
        self.file_ok_string_edit.setEnabled(
            self.file_ok_group.isEnabled() and self.file_ok_string_check.isChecked()
        )
        self.file_nok_string_edit.setEnabled(
            self.file_nok_group.isEnabled() and self.file_nok_string_check.isChecked()
        )

    def _update_file_actions_mode_ui(self) -> None:
        if not hasattr(self, "file_actions_enable_check"):
            return

        source_enabled = self.file_actions_enable_check.isChecked() and self.file_actions_enable_check.isEnabled()
        json_enabled = self.file_actions_save_json_check.isChecked()
        processed_enabled = self.file_actions_save_processed_check.isChecked()
        enabled = source_enabled or json_enabled or processed_enabled
        mode = str(self.file_actions_mode_combo.currentData() or "move_by_result")
        self.file_actions_mode_combo.setEnabled(source_enabled)

        if not enabled:
            ok_needs_target = False
            nok_needs_target = False
        elif source_enabled:
            ok_needs_target = mode in {"move_by_result", "move_ok_delete_nok"}
            nok_needs_target = mode in {"move_by_result", "delete_ok_move_nok"}
            if json_enabled or processed_enabled:
                ok_needs_target = True
                nok_needs_target = True
        else:
            ok_needs_target = True
            nok_needs_target = True

        self.file_ok_group.setEnabled(ok_needs_target)
        self.file_nok_group.setEnabled(nok_needs_target)
        self._update_file_actions_string_edits()

    def _build_log_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.log_tab)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def _build_json_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.json_tab)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        self.json_view = QtWidgets.QTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setPlainText("{}")
        layout.addWidget(self.json_view)

    def _build_audio_tab(self) -> None:
        _, root = self._build_scroll_tab_root(self.audio_tab)

        common_group = QtWidgets.QGroupBox("Společné nastavení")
        self.audio_common_group = common_group
        common_form = QtWidgets.QFormLayout(common_group)
        self._apply_compact_form_layout(common_form)

        self.audio_enable_check = QtWidgets.QCheckBox("Povolit Sound camera")
        self.audio_approach_combo = QtWidgets.QComboBox()
        self.audio_approach_combo.addItem("Payload", "payload")
        self.audio_approach_combo.addItem("Lissajous", "lissajous")
        self.audio_approach_combo.addItem("Classic", "classic")
        self.audio_source_combo = QtWidgets.QComboBox()
        self.audio_source_combo.addItem("Loopback (systémový výstup)", "loopback")
        self.audio_source_combo.addItem("Microphone", "microphone")
        self.audio_source_combo.addItem("Sine (test)", "sine")

        self.audio_device_combo = QtWidgets.QComboBox()
        self.audio_refresh_devices_btn = QtWidgets.QPushButton("Obnovit zařízení")
        self.audio_refresh_devices_btn.clicked.connect(self._refresh_audio_devices)
        device_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(device_layout)
        device_layout.addWidget(self.audio_device_combo)
        device_layout.addWidget(self.audio_refresh_devices_btn)

        self.audio_backend_policy_combo = QtWidgets.QComboBox()
        self.audio_backend_policy_combo.addItem("Auto (doporučeno)", "auto")
        self.audio_backend_policy_combo.addItem("Prefer pyaudiowpatch", "prefer_pyaudiowpatch")
        self.audio_backend_policy_combo.addItem("Pouze sounddevice", "sounddevice_only")

        self.audio_send_mode_combo = QtWidgets.QComboBox()
        self.audio_send_mode_combo.addItem("Save+Send", "save_send")
        self.audio_send_mode_combo.addItem("Send-only", "send_only")
        self.audio_send_mode_combo.currentIndexChanged.connect(self._update_sound_send_mode_ui)

        self.audio_sample_rate_spin = QtWidgets.QSpinBox()
        self.audio_sample_rate_spin.setRange(8000, 192000)
        self.audio_sample_rate_spin.setSingleStep(1000)
        self.audio_sample_rate_spin.setValue(16000)
        self.audio_window_spin = QtWidgets.QDoubleSpinBox()
        self.audio_window_spin.setDecimals(2)
        self.audio_window_spin.setRange(0.1, 60.0)
        self.audio_window_spin.setValue(1.0)
        self.audio_window_spin.setSuffix(" s")
        self.audio_fps_spin = QtWidgets.QDoubleSpinBox()
        self.audio_fps_spin.setDecimals(3)
        self.audio_fps_spin.setRange(0.001, 10.0)
        self.audio_fps_spin.setValue(0.5)
        self.audio_fps_spin.setSuffix(" FPS")
        self.audio_sine_freq_spin = QtWidgets.QDoubleSpinBox()
        self.audio_sine_freq_spin.setDecimals(1)
        self.audio_sine_freq_spin.setRange(20.0, 20000.0)
        self.audio_sine_freq_spin.setValue(440.0)
        self.audio_sine_freq_spin.setSuffix(" Hz")
        self.audio_fps_info_label = QtWidgets.QLabel("")
        self.audio_fps_info_label.setStyleSheet("color: #666;")

        self.audio_snapshot_dir_edit = QtWidgets.QLineEdit("sound_camera_snapshots")
        self.audio_snapshot_dir_btn = QtWidgets.QPushButton("Vybrat složku")
        self.audio_snapshot_dir_btn.clicked.connect(self._select_audio_snapshot_dir)
        snapshot_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(snapshot_layout)
        snapshot_layout.addWidget(self.audio_snapshot_dir_edit)
        snapshot_layout.addWidget(self.audio_snapshot_dir_btn)
        self.audio_file_prefix_edit = QtWidgets.QLineEdit("sound")

        preview_btn_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(preview_btn_layout)
        self.audio_preview_start_btn = QtWidgets.QPushButton("Start preview")
        self.audio_preview_stop_btn = QtWidgets.QPushButton("Stop preview")
        self.audio_preview_show_btn = QtWidgets.QPushButton("Ukázat preview")
        preview_btn_layout.addWidget(self.audio_preview_start_btn)
        preview_btn_layout.addWidget(self.audio_preview_stop_btn)
        preview_btn_layout.addWidget(self.audio_preview_show_btn)
        self.audio_preview_start_btn.clicked.connect(self._start_sound_preview)
        self.audio_preview_stop_btn.clicked.connect(self._stop_sound_preview)
        self.audio_preview_show_btn.clicked.connect(self._open_sound_preview_dialog)

        self.audio_device_status_label = QtWidgets.QLabel("")
        self.audio_device_status_label.setStyleSheet("color: #666;")

        common_form.addRow("", self.audio_enable_check)
        common_form.addRow("Přístup", self.audio_approach_combo)
        common_form.addRow("Zdroj", self.audio_source_combo)
        common_form.addRow("Zařízení", device_layout)
        common_form.addRow("Backend policy", self.audio_backend_policy_combo)
        common_form.addRow("Režim odesílání", self.audio_send_mode_combo)
        common_form.addRow("Sample rate", self.audio_sample_rate_spin)
        common_form.addRow("Délka snímku", self.audio_window_spin)
        common_form.addRow("FPS", self.audio_fps_spin)
        common_form.addRow("", self.audio_fps_info_label)
        common_form.addRow("Sine frequency", self.audio_sine_freq_spin)
        common_form.addRow("Snapshot složka", snapshot_layout)
        common_form.addRow("Prefix souboru", self.audio_file_prefix_edit)
        common_form.addRow("", preview_btn_layout)
        common_form.addRow("", self.audio_device_status_label)
        root.addWidget(common_group, 0)

        self.audio_settings_stack = QtWidgets.QStackedWidget()

        payload_page = QtWidgets.QWidget()
        payload_form = QtWidgets.QFormLayout(payload_page)
        self._apply_compact_form_layout(payload_form)
        self.payload_frame_seconds_spin = QtWidgets.QDoubleSpinBox()
        self.payload_frame_seconds_spin.setDecimals(2)
        self.payload_frame_seconds_spin.setRange(0.2, 4.0)
        self.payload_frame_seconds_spin.setValue(1.0)
        self.payload_frame_seconds_spin.setSuffix(" s")
        self.payload_overlap_combo = QtWidgets.QComboBox()
        for value in [0, 10, 25, 33, 50, 66, 75]:
            self.payload_overlap_combo.addItem(f"{value} %", value)
        self.payload_overlap_combo.setCurrentIndex(4)
        self.payload_style_combo = QtWidgets.QComboBox()
        self.payload_style_combo.addItem("stack3", "stack3")
        self.payload_style_combo.addItem("raw_stream", "raw_stream")
        self.payload_style_combo.addItem("bitplane_transpose", "bitplane_transpose")
        self.payload_style_combo.addItem("delta_bitplane_transpose", "delta_bitplane_transpose")
        self.payload_y_repeat_combo = QtWidgets.QComboBox()
        for value in [1, 2, 4]:
            self.payload_y_repeat_combo.addItem(str(value), value)
        self.payload_y_repeat_combo.setCurrentIndex(2)
        self.payload_variant_combo = QtWidgets.QComboBox()
        for item in [
            "none",
            "perm_rgb",
            "perm_rbg",
            "perm_grb",
            "perm_gbr",
            "perm_brg",
            "invert_all",
            "invert_r",
            "invert_g",
            "invert_b",
            "xor80_all",
            "dark_gray_06",
            "dark_turbo_04",
        ]:
            self.payload_variant_combo.addItem(item, item)
        self.payload_preview_resize_combo = QtWidgets.QComboBox()
        self.payload_preview_resize_combo.addItem("pixel", "pixel")
        self.payload_preview_resize_combo.addItem("smooth", "smooth")
        self.payload_overlay_grid_check = QtWidgets.QCheckBox("Zobrazit rastr")
        self.payload_overlay_grid_check.setChecked(True)
        self.payload_overlay_time_check = QtWidgets.QCheckBox("Zobrazit časové značky")
        self.payload_overlay_time_check.setChecked(True)
        self.payload_overlay_stack_check = QtWidgets.QCheckBox("Zobrazit hranice stacku")
        self.payload_overlay_stack_check.setChecked(True)
        self.payload_overlay_legend_check = QtWidgets.QCheckBox("Zobrazit popisek")
        self.payload_overlay_legend_check.setChecked(True)
        self.payload_formula_label = QtWidgets.QLabel("")
        self.payload_formula_label.setStyleSheet("color: #666;")
        payload_form.addRow("Frame seconds", self.payload_frame_seconds_spin)
        payload_form.addRow("Overlap", self.payload_overlap_combo)
        payload_form.addRow("Style", self.payload_style_combo)
        payload_form.addRow("Y repeat", self.payload_y_repeat_combo)
        payload_form.addRow("Variant", self.payload_variant_combo)
        payload_form.addRow("Preview resize", self.payload_preview_resize_combo)
        payload_form.addRow("", self.payload_overlay_grid_check)
        payload_form.addRow("", self.payload_overlay_time_check)
        payload_form.addRow("", self.payload_overlay_stack_check)
        payload_form.addRow("", self.payload_overlay_legend_check)
        payload_form.addRow("", self.payload_formula_label)
        self.audio_settings_stack.addWidget(payload_page)

        liss_page = QtWidgets.QWidget()
        liss_form = QtWidgets.QFormLayout(liss_page)
        self._apply_compact_form_layout(liss_form)
        self.liss_tau_combo = QtWidgets.QComboBox()
        for tau in [1, 5, 10, 20, 50, "both"]:
            self.liss_tau_combo.addItem(str(tau), tau)
        self.liss_tau_combo.setCurrentIndex(1)
        self.liss_width_spin = QtWidgets.QSpinBox()
        self.liss_width_spin.setRange(128, 4096)
        self.liss_width_spin.setValue(512)
        self.liss_height_spin = QtWidgets.QSpinBox()
        self.liss_height_spin.setRange(128, 4096)
        self.liss_height_spin.setValue(512)
        self.liss_accum_combo = QtWidgets.QComboBox()
        for mode in ["none", "max", "sum", "avg"]:
            self.liss_accum_combo.addItem(mode, mode)
        self.liss_point_size_spin = QtWidgets.QSpinBox()
        self.liss_point_size_spin.setRange(1, 7)
        self.liss_point_size_spin.setValue(1)
        self.liss_point_style_combo = QtWidgets.QComboBox()
        for mode in ["classic", "sharp_stamp", "square_stamp"]:
            self.liss_point_style_combo.addItem(mode, mode)
        self.liss_value_mode_combo = QtWidgets.QComboBox()
        for mode in ["radial", "flat"]:
            self.liss_value_mode_combo.addItem(mode, mode)
        self.liss_rotation_combo = QtWidgets.QComboBox()
        for mode in ["none", "plus45", "minus45"]:
            self.liss_rotation_combo.addItem(mode, mode)
        liss_form.addRow("Tau", self.liss_tau_combo)
        liss_form.addRow("Width", self.liss_width_spin)
        liss_form.addRow("Height", self.liss_height_spin)
        liss_form.addRow("Accum", self.liss_accum_combo)
        liss_form.addRow("Point size step", self.liss_point_size_spin)
        liss_form.addRow("Point style", self.liss_point_style_combo)
        liss_form.addRow("Value mode", self.liss_value_mode_combo)
        liss_form.addRow("Rotation", self.liss_rotation_combo)
        self.audio_settings_stack.addWidget(liss_page)

        classic_page = QtWidgets.QWidget()
        classic_root = QtWidgets.QVBoxLayout(classic_page)
        self._apply_compact_box_layout(classic_root)

        basic_group = QtWidgets.QGroupBox("Základní nastavení")
        basic_grid = QtWidgets.QGridLayout(basic_group)
        self._apply_compact_box_layout(basic_grid)
        basic_grid.setColumnStretch(1, 1)
        basic_grid.setColumnStretch(3, 1)

        self.classic_preset_combo = QtWidgets.QComboBox()
        self.classic_preset_combo.addItem("none", "none")
        self.classic_preset_combo.addItem("classic_fhd", "classic_fhd")
        self.classic_preset_combo.addItem("classic_impulse", "classic_impulse")
        self.classic_style_combo = QtWidgets.QComboBox()
        self.classic_style_combo.addItem("CLASSIC", "classic")
        self.classic_style_combo.addItem("FUSE7", "fuse7")
        self.classic_style_combo.addItem("FUSE4_base", "fuse4_base")
        self.classic_axis_combo = QtWidgets.QComboBox()
        self.classic_axis_combo.addItem("Linear", "linear")
        self.classic_axis_combo.addItem("Log", "log")
        self.classic_axis_combo.addItem("Mel", "mel")
        self.classic_width_spin = QtWidgets.QSpinBox()
        self.classic_width_spin.setRange(128, 4096)
        self.classic_width_spin.setValue(1024)
        self.classic_height_spin = QtWidgets.QSpinBox()
        self.classic_height_spin.setRange(128, 4096)
        self.classic_height_spin.setValue(768)
        self.classic_colormap_combo = QtWidgets.QComboBox()
        for mode in ["gray", "none", "turbo", "viridis", "magma"]:
            self.classic_colormap_combo.addItem(mode, mode)
        self.classic_gamma_spin = QtWidgets.QDoubleSpinBox()
        self.classic_gamma_spin.setDecimals(2)
        self.classic_gamma_spin.setRange(0.1, 8.0)
        self.classic_gamma_spin.setValue(1.0)
        self.classic_mode_status_label = QtWidgets.QLabel("")
        self.classic_mode_status_label.setStyleSheet("color: #666;")
        self.classic_overlap_info_label = QtWidgets.QLabel("")
        self.classic_overlap_info_label.setStyleSheet("color: #666;")

        basic_grid.addWidget(QtWidgets.QLabel("Preset"), 0, 0)
        basic_grid.addWidget(self.classic_preset_combo, 0, 1)
        basic_grid.addWidget(QtWidgets.QLabel("Styl"), 0, 2)
        basic_grid.addWidget(self.classic_style_combo, 0, 3)
        basic_grid.addWidget(QtWidgets.QLabel("Colormap"), 1, 0)
        basic_grid.addWidget(self.classic_colormap_combo, 1, 1)
        basic_grid.addWidget(QtWidgets.QLabel("Osa Y"), 1, 2)
        basic_grid.addWidget(self.classic_axis_combo, 1, 3)
        basic_grid.addWidget(QtWidgets.QLabel("W"), 2, 0)
        basic_grid.addWidget(self.classic_width_spin, 2, 1)
        basic_grid.addWidget(QtWidgets.QLabel("H"), 2, 2)
        basic_grid.addWidget(self.classic_height_spin, 2, 3)
        basic_grid.addWidget(QtWidgets.QLabel("Gamma"), 3, 0)
        basic_grid.addWidget(self.classic_gamma_spin, 3, 1)
        basic_grid.addWidget(self.classic_mode_status_label, 3, 2, 1, 2)
        basic_grid.addWidget(self.classic_overlap_info_label, 4, 0, 1, 4)

        advanced_group = QtWidgets.QGroupBox("Pokročilé nastavení")
        advanced_layout = QtWidgets.QHBoxLayout(advanced_group)
        self._apply_compact_box_layout(advanced_layout)

        stft_box = QtWidgets.QGroupBox("STFT + detail")
        stft_grid = QtWidgets.QGridLayout(stft_box)
        self._apply_compact_box_layout(stft_grid)
        stft_grid.setColumnStretch(1, 1)
        stft_grid.setColumnStretch(3, 1)

        self.classic_n_fft_spin = QtWidgets.QSpinBox()
        self.classic_n_fft_spin.setRange(256, 131072)
        self.classic_n_fft_spin.setSingleStep(256)
        self.classic_n_fft_spin.setValue(4096)
        self.classic_win_ms_spin = QtWidgets.QDoubleSpinBox()
        self.classic_win_ms_spin.setDecimals(2)
        self.classic_win_ms_spin.setRange(1.0, 500.0)
        self.classic_win_ms_spin.setSingleStep(0.5)
        self.classic_win_ms_spin.setValue(25.0)
        self.classic_win_ms_spin.setSuffix(" ms")
        self.classic_hop_ms_spin = QtWidgets.QDoubleSpinBox()
        self.classic_hop_ms_spin.setDecimals(3)
        self.classic_hop_ms_spin.setRange(0.01, 500.0)
        self.classic_hop_ms_spin.setSingleStep(0.1)
        self.classic_hop_ms_spin.setValue(1.0)
        self.classic_hop_ms_spin.setSuffix(" ms")
        self.classic_top_db_spin = QtWidgets.QDoubleSpinBox()
        self.classic_top_db_spin.setDecimals(1)
        self.classic_top_db_spin.setRange(10.0, 180.0)
        self.classic_top_db_spin.setSingleStep(1.0)
        self.classic_top_db_spin.setValue(80.0)
        self.classic_fmax_spin = QtWidgets.QDoubleSpinBox()
        self.classic_fmax_spin.setDecimals(1)
        self.classic_fmax_spin.setRange(100.0, 96000.0)
        self.classic_fmax_spin.setSingleStep(100.0)
        self.classic_fmax_spin.setValue(24000.0)
        self.classic_fmax_spin.setSuffix(" Hz")
        self.classic_detail_mode_combo = QtWidgets.QComboBox()
        for mode in ["off", "highpass", "edgesobel"]:
            self.classic_detail_mode_combo.addItem(mode, mode)
        self.classic_detail_sigma_spin = QtWidgets.QDoubleSpinBox()
        self.classic_detail_sigma_spin.setDecimals(2)
        self.classic_detail_sigma_spin.setRange(0.1, 24.0)
        self.classic_detail_sigma_spin.setValue(1.2)
        self.classic_detail_gain_spin = QtWidgets.QDoubleSpinBox()
        self.classic_detail_gain_spin.setDecimals(1)
        self.classic_detail_gain_spin.setRange(0.0, 1000.0)
        self.classic_detail_gain_spin.setValue(70.0)
        self.classic_detail_p_spin = QtWidgets.QDoubleSpinBox()
        self.classic_detail_p_spin.setDecimals(2)
        self.classic_detail_p_spin.setRange(1.0, 99.99)
        self.classic_detail_p_spin.setValue(99.5)
        self.classic_freq_interp_combo = QtWidgets.QComboBox()
        for mode in ["auto", "area", "linear", "nearest"]:
            self.classic_freq_interp_combo.addItem(mode, mode)

        stft_grid.addWidget(QtWidgets.QLabel("N FFT"), 0, 0)
        stft_grid.addWidget(self.classic_n_fft_spin, 0, 1)
        stft_grid.addWidget(QtWidgets.QLabel("Win ms"), 0, 2)
        stft_grid.addWidget(self.classic_win_ms_spin, 0, 3)
        stft_grid.addWidget(QtWidgets.QLabel("Hop ms"), 1, 0)
        stft_grid.addWidget(self.classic_hop_ms_spin, 1, 1)
        stft_grid.addWidget(QtWidgets.QLabel("Top dB"), 1, 2)
        stft_grid.addWidget(self.classic_top_db_spin, 1, 3)
        stft_grid.addWidget(QtWidgets.QLabel("Fmax"), 2, 0)
        stft_grid.addWidget(self.classic_fmax_spin, 2, 1)
        stft_grid.addWidget(QtWidgets.QLabel("Freq interp"), 2, 2)
        stft_grid.addWidget(self.classic_freq_interp_combo, 2, 3)
        stft_grid.addWidget(QtWidgets.QLabel("Detail mode"), 3, 0)
        stft_grid.addWidget(self.classic_detail_mode_combo, 3, 1)
        stft_grid.addWidget(QtWidgets.QLabel("Detail sigma"), 3, 2)
        stft_grid.addWidget(self.classic_detail_sigma_spin, 3, 3)
        stft_grid.addWidget(QtWidgets.QLabel("Detail gain"), 4, 0)
        stft_grid.addWidget(self.classic_detail_gain_spin, 4, 1)
        stft_grid.addWidget(QtWidgets.QLabel("Detail p"), 4, 2)
        stft_grid.addWidget(self.classic_detail_p_spin, 4, 3)

        fuse_box = QtWidgets.QGroupBox("FUSE parametry")
        fuse_grid = QtWidgets.QGridLayout(fuse_box)
        self._apply_compact_box_layout(fuse_grid)
        fuse_grid.setColumnStretch(1, 1)
        fuse_grid.setColumnStretch(3, 1)

        self.classic_fuse7_profile_combo = QtWidgets.QComboBox()
        for mode in ["ref_compat", "default"]:
            self.classic_fuse7_profile_combo.addItem(mode, mode)
        self.classic_scale_mode_combo = QtWidgets.QComboBox()
        for mode in ["top_db", "percentile"]:
            self.classic_scale_mode_combo.addItem(mode, mode)
        self.classic_p_lo_spin = QtWidgets.QDoubleSpinBox()
        self.classic_p_lo_spin.setDecimals(2)
        self.classic_p_lo_spin.setRange(0.0, 99.0)
        self.classic_p_lo_spin.setSingleStep(0.1)
        self.classic_p_lo_spin.setValue(1.0)
        self.classic_p_hi_spin = QtWidgets.QDoubleSpinBox()
        self.classic_p_hi_spin.setDecimals(2)
        self.classic_p_hi_spin.setRange(1.0, 100.0)
        self.classic_p_hi_spin.setSingleStep(0.1)
        self.classic_p_hi_spin.setValue(99.0)
        self.classic_n_mels_hue_spin = QtWidgets.QSpinBox()
        self.classic_n_mels_hue_spin.setRange(8, 512)
        self.classic_n_mels_hue_spin.setSingleStep(8)
        self.classic_n_mels_hue_spin.setValue(128)
        self.classic_n_mels_layers_spin = QtWidgets.QSpinBox()
        self.classic_n_mels_layers_spin.setRange(8, 512)
        self.classic_n_mels_layers_spin.setSingleStep(8)
        self.classic_n_mels_layers_spin.setValue(64)
        self.classic_norm_p_spin = QtWidgets.QDoubleSpinBox()
        self.classic_norm_p_spin.setDecimals(2)
        self.classic_norm_p_spin.setRange(1.0, 100.0)
        self.classic_norm_p_spin.setSingleStep(0.1)
        self.classic_norm_p_spin.setValue(99.5)
        self.classic_flux_gain_spin = QtWidgets.QDoubleSpinBox()
        self.classic_flux_gain_spin.setDecimals(1)
        self.classic_flux_gain_spin.setRange(0.0, 1000.0)
        self.classic_flux_gain_spin.setSingleStep(1.0)
        self.classic_flux_gain_spin.setValue(110.0)
        self.classic_edge_gain_spin = QtWidgets.QDoubleSpinBox()
        self.classic_edge_gain_spin.setDecimals(1)
        self.classic_edge_gain_spin.setRange(0.0, 1000.0)
        self.classic_edge_gain_spin.setSingleStep(1.0)
        self.classic_edge_gain_spin.setValue(70.0)
        self.classic_freq_green_bias_spin = QtWidgets.QDoubleSpinBox()
        self.classic_freq_green_bias_spin.setDecimals(3)
        self.classic_freq_green_bias_spin.setRange(-2.0, 2.0)
        self.classic_freq_green_bias_spin.setSingleStep(0.01)
        self.classic_freq_green_bias_spin.setValue(0.15)
        self.classic_edge_base_alpha_spin = QtWidgets.QDoubleSpinBox()
        self.classic_edge_base_alpha_spin.setDecimals(3)
        self.classic_edge_base_alpha_spin.setRange(0.0, 1.0)
        self.classic_edge_base_alpha_spin.setSingleStep(0.01)
        self.classic_edge_base_alpha_spin.setValue(0.25)

        fuse_grid.addWidget(QtWidgets.QLabel("FUSE profile"), 0, 0)
        fuse_grid.addWidget(self.classic_fuse7_profile_combo, 0, 1)
        fuse_grid.addWidget(QtWidgets.QLabel("Scale mode"), 0, 2)
        fuse_grid.addWidget(self.classic_scale_mode_combo, 0, 3)
        fuse_grid.addWidget(QtWidgets.QLabel("p_lo"), 1, 0)
        fuse_grid.addWidget(self.classic_p_lo_spin, 1, 1)
        fuse_grid.addWidget(QtWidgets.QLabel("p_hi"), 1, 2)
        fuse_grid.addWidget(self.classic_p_hi_spin, 1, 3)
        fuse_grid.addWidget(QtWidgets.QLabel("n_mels_hue"), 2, 0)
        fuse_grid.addWidget(self.classic_n_mels_hue_spin, 2, 1)
        fuse_grid.addWidget(QtWidgets.QLabel("n_mels_layers"), 2, 2)
        fuse_grid.addWidget(self.classic_n_mels_layers_spin, 2, 3)
        fuse_grid.addWidget(QtWidgets.QLabel("norm_p"), 3, 0)
        fuse_grid.addWidget(self.classic_norm_p_spin, 3, 1)
        fuse_grid.addWidget(QtWidgets.QLabel("flux_gain"), 3, 2)
        fuse_grid.addWidget(self.classic_flux_gain_spin, 3, 3)
        fuse_grid.addWidget(QtWidgets.QLabel("edge_gain"), 4, 0)
        fuse_grid.addWidget(self.classic_edge_gain_spin, 4, 1)
        fuse_grid.addWidget(QtWidgets.QLabel("freq_green_bias"), 4, 2)
        fuse_grid.addWidget(self.classic_freq_green_bias_spin, 4, 3)
        fuse_grid.addWidget(QtWidgets.QLabel("edge_base_alpha"), 5, 0)
        fuse_grid.addWidget(self.classic_edge_base_alpha_spin, 5, 1)

        advanced_layout.addWidget(stft_box, 1)
        advanced_layout.addWidget(fuse_box, 1)
        self.classic_fuse_box = fuse_box
        self.classic_advanced_group = advanced_group

        self.classic_advanced_btn = QtWidgets.QPushButton("Pokročilé nastavení...")
        self.classic_advanced_btn.clicked.connect(self._open_classic_advanced_dialog)

        classic_root.addWidget(basic_group)
        classic_root.addWidget(self.classic_advanced_btn, 0, QtCore.Qt.AlignLeft)
        classic_root.addStretch(1)
        self.audio_settings_stack.addWidget(classic_page)

        root.addWidget(QtWidgets.QLabel("Nastavení podle přístupu"))
        root.addWidget(self.audio_settings_stack, 1)

        self.audio_approach_combo.currentIndexChanged.connect(self._update_audio_stack)
        self.audio_source_combo.currentIndexChanged.connect(self._on_audio_source_changed)
        self.audio_enable_check.toggled.connect(self._update_file_actions_loop_state)
        self.audio_enable_check.toggled.connect(self._update_sound_send_mode_ui)
        self.classic_preset_combo.currentIndexChanged.connect(self._apply_classic_preset_template)
        self.classic_style_combo.currentIndexChanged.connect(self._update_classic_style_ui)
        self.classic_axis_combo.currentIndexChanged.connect(self._update_classic_style_ui)
        self.audio_window_spin.valueChanged.connect(self._update_sound_formula_labels)
        self.audio_fps_spin.valueChanged.connect(self._update_sound_formula_labels)
        self.payload_frame_seconds_spin.valueChanged.connect(self._update_sound_formula_labels)
        self.payload_overlap_combo.currentIndexChanged.connect(self._update_sound_formula_labels)
        self._connect_sound_preview_reconfigure_signals()
        self._update_audio_stack()
        self._refresh_audio_devices()
        self._update_sound_send_mode_ui()
        self._update_sound_formula_labels()
        self._update_classic_style_ui()
        self._update_sound_preview_buttons()

    def _ensure_classic_advanced_dialog(self) -> QtWidgets.QDialog:
        if self.classic_advanced_dialog is None:
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Classic - Pokročilé nastavení")
            dialog.setModal(False)
            dialog.resize(900, 620)
            layout = QtWidgets.QVBoxLayout(dialog)
            self._apply_compact_box_layout(layout)
            info_label = QtWidgets.QLabel(
                "Pokročilé parametry pro styl CLASSIC a FUSE režimy."
            )
            info_label.setStyleSheet("color: #666;")
            layout.addWidget(info_label)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setWidget(self.classic_advanced_group)
            layout.addWidget(scroll, 1)
            close_btn = QtWidgets.QPushButton("Zavřít")
            close_btn.clicked.connect(dialog.hide)
            layout.addWidget(close_btn, 0, QtCore.Qt.AlignRight)
            self.classic_advanced_dialog = dialog
        return self.classic_advanced_dialog

    def _open_classic_advanced_dialog(self) -> None:
        dialog = self._ensure_classic_advanced_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _select_audio_snapshot_dir(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Vyberte složku pro Sound camera snapshoty")
        if folder:
            self.audio_snapshot_dir_edit.setText(folder)

    def _refresh_audio_devices(self, selected_device: str = "") -> None:
        self.audio_device_combo.clear()
        source = str(self.audio_source_combo.currentData() or "loopback")
        default_label = "Default loopback output" if source == "loopback" else "Default system microphone"
        self.audio_device_combo.addItem(default_label, "default")
        available_count = 0
        selected = selected_device.strip() if isinstance(selected_device, str) else ""
        try:
            if source == "loopback":
                rows = list_loopback_devices()
            elif source == "microphone":
                rows = list_microphone_devices()
            else:
                rows = [{"id": "default", "label": "Sine source (no device needed)"}]
            for row in rows:
                label = str(row.get("label", "unknown"))
                device_id = str(row.get("id", "default"))
                if device_id == "default":
                    continue
                self.audio_device_combo.addItem(label, device_id)
                available_count += 1
        except Exception as exc:
            if selected:
                self.audio_device_combo.addItem(f"{selected} (uložené)", selected)
                self.audio_device_combo.setCurrentIndex(self.audio_device_combo.count() - 1)
            self.audio_device_status_label.setText(f"Detekce mikrofonu selhala: {exc}")
            return

        if selected:
            found = False
            for idx in range(self.audio_device_combo.count()):
                if str(self.audio_device_combo.itemData(idx) or "") == selected:
                    self.audio_device_combo.setCurrentIndex(idx)
                    found = True
                    break
            if not found:
                self.audio_device_combo.addItem(f"{selected} (uložené)", selected)
                self.audio_device_combo.setCurrentIndex(self.audio_device_combo.count() - 1)

        mode_info = "loopback" if source == "loopback" else "microphone" if source == "microphone" else "sine"
        self.audio_device_status_label.setText(
            f"Nalezeno zařízení ({mode_info}): {available_count}"
        )

    def _on_audio_source_changed(self) -> None:
        self._refresh_audio_devices()
        sending = bool(self.state.runner and self.state.runner.get_status() != "stopped")
        is_sine = str(self.audio_source_combo.currentData() or "") == "sine"
        self.audio_device_combo.setEnabled(not is_sine and not sending)
        self.audio_refresh_devices_btn.setEnabled(not is_sine and not sending)
        self.audio_sine_freq_spin.setEnabled(is_sine and not sending)
        self._schedule_sound_preview_reconfigure()

    def _update_audio_stack(self) -> None:
        approach = str(self.audio_approach_combo.currentData() or "payload")
        index = {"payload": 0, "lissajous": 1, "classic": 2}.get(approach, 0)
        self.audio_settings_stack.setCurrentIndex(index)
        self._update_classic_style_ui()
        self._update_sound_formula_labels()
        self._schedule_sound_preview_reconfigure()

    def _update_classic_style_ui(self) -> None:
        style = str(self.classic_style_combo.currentData() or "classic")
        is_classic = style == "classic"
        is_fuse = style in {"fuse7", "fuse4_base"}

        self.classic_axis_combo.setEnabled(is_classic)
        self.classic_colormap_combo.setEnabled(is_classic)
        self.classic_gamma_spin.setEnabled(is_classic)
        self.classic_detail_mode_combo.setEnabled(is_classic)
        self.classic_detail_sigma_spin.setEnabled(is_classic)
        self.classic_detail_gain_spin.setEnabled(is_classic)
        self.classic_detail_p_spin.setEnabled(is_classic)
        self.classic_freq_interp_combo.setEnabled(is_classic)
        if hasattr(self, "classic_fuse_box"):
            self.classic_fuse_box.setEnabled(is_fuse)

        axis = str(self.classic_axis_combo.currentData() or "linear")
        if is_classic:
            self.classic_mode_status_label.setText(f"Styl CLASSIC | osa Y: {axis}")
        elif style == "fuse7":
            self.classic_mode_status_label.setText("Styl FUSE7 | osa Y se nepouziva")
        else:
            self.classic_mode_status_label.setText("Styl FUSE4_base | osa Y se nepouziva")

    def _update_sound_send_mode_ui(self) -> None:
        send_mode = str(self.audio_send_mode_combo.currentData() or "save_send")
        sending = bool(self.state.runner and self.state.runner.get_status() != "stopped")
        save_send = send_mode == "save_send"
        is_sine = str(self.audio_source_combo.currentData() or "") == "sine"
        self.audio_snapshot_dir_edit.setEnabled(save_send and not sending)
        self.audio_snapshot_dir_btn.setEnabled(save_send and not sending)
        self.audio_file_prefix_edit.setEnabled(not sending)
        self.audio_device_combo.setEnabled(not is_sine and not sending)
        self.audio_refresh_devices_btn.setEnabled(not is_sine and not sending)
        self.audio_sine_freq_spin.setEnabled(is_sine and not sending)
        if not save_send and self.audio_enable_check.isChecked():
            self.audio_device_status_label.setText(
                "Send-only: zdrojové move/delete akce budou při běhu vypnuté."
            )
        elif self.audio_device_status_label.text().startswith("Send-only:"):
            self.audio_device_status_label.setText("")
        self._update_file_actions_loop_state()

    def _connect_sound_preview_reconfigure_signals(self) -> None:
        controls = [
            self.audio_enable_check,
            self.audio_approach_combo,
            self.audio_source_combo,
            self.audio_device_combo,
            self.audio_backend_policy_combo,
            self.audio_send_mode_combo,
            self.audio_sample_rate_spin,
            self.audio_window_spin,
            self.audio_fps_spin,
            self.audio_sine_freq_spin,
            self.audio_snapshot_dir_edit,
            self.audio_file_prefix_edit,
            self.payload_frame_seconds_spin,
            self.payload_overlap_combo,
            self.payload_style_combo,
            self.payload_y_repeat_combo,
            self.payload_variant_combo,
            self.payload_preview_resize_combo,
            self.payload_overlay_grid_check,
            self.payload_overlay_time_check,
            self.payload_overlay_stack_check,
            self.payload_overlay_legend_check,
            self.liss_tau_combo,
            self.liss_width_spin,
            self.liss_height_spin,
            self.liss_accum_combo,
            self.liss_point_size_spin,
            self.liss_point_style_combo,
            self.liss_value_mode_combo,
            self.liss_rotation_combo,
            self.classic_preset_combo,
            self.classic_style_combo,
            self.classic_axis_combo,
            self.classic_width_spin,
            self.classic_height_spin,
            self.classic_colormap_combo,
            self.classic_gamma_spin,
            self.classic_n_fft_spin,
            self.classic_win_ms_spin,
            self.classic_hop_ms_spin,
            self.classic_top_db_spin,
            self.classic_fmax_spin,
            self.classic_detail_mode_combo,
            self.classic_detail_sigma_spin,
            self.classic_detail_gain_spin,
            self.classic_detail_p_spin,
            self.classic_freq_interp_combo,
            self.classic_fuse7_profile_combo,
            self.classic_scale_mode_combo,
            self.classic_p_lo_spin,
            self.classic_p_hi_spin,
            self.classic_n_mels_hue_spin,
            self.classic_n_mels_layers_spin,
            self.classic_norm_p_spin,
            self.classic_flux_gain_spin,
            self.classic_edge_gain_spin,
            self.classic_freq_green_bias_spin,
            self.classic_edge_base_alpha_spin,
        ]
        for widget in controls:
            if isinstance(widget, QtWidgets.QComboBox):
                widget.currentIndexChanged.connect(self._schedule_sound_preview_reconfigure)
            elif isinstance(widget, QtWidgets.QAbstractSpinBox):
                widget.editingFinished.connect(self._schedule_sound_preview_reconfigure)
            elif isinstance(widget, QtWidgets.QCheckBox):
                widget.toggled.connect(self._schedule_sound_preview_reconfigure)
            elif isinstance(widget, QtWidgets.QLineEdit):
                widget.editingFinished.connect(self._schedule_sound_preview_reconfigure)

    def _schedule_sound_preview_reconfigure(self) -> None:
        if self.sound_preview_controller and self.sound_preview_controller.is_running():
            self.sound_preview_reconfig_timer.start()

    def _reconfigure_sound_preview_from_gui(self) -> None:
        if not (self.sound_preview_controller and self.sound_preview_controller.is_running()):
            return
        try:
            cfg = self._gather_config()
        except Exception as exc:
            self.audio_device_status_label.setText(f"Preview reconfigure error: {exc}")
            return
        self.sound_preview_controller.reconfigure(cfg)
        self.audio_device_status_label.setText("Preview reconfigure: použito nové nastavení.")

    def _apply_classic_preset_template(self, *_args) -> None:
        preset = str(self.classic_preset_combo.currentData() or "none")
        if preset == "classic_fhd":
            self.classic_width_spin.setValue(1920)
            self.classic_height_spin.setValue(1080)
            self.classic_n_fft_spin.setValue(8192)
            self.classic_win_ms_spin.setValue(40.0)
            self.classic_hop_ms_spin.setValue(0.5)
            self.classic_top_db_spin.setValue(80.0)
            self.classic_fmax_spin.setValue(24000.0)
            self.classic_colormap_combo.setCurrentText("gray")
            self.classic_gamma_spin.setValue(1.0)
            self.classic_detail_mode_combo.setCurrentText("highpass")
            self.classic_detail_sigma_spin.setValue(1.2)
            self.classic_detail_gain_spin.setValue(70.0)
            self.classic_detail_p_spin.setValue(99.5)
            self.classic_freq_interp_combo.setCurrentText("auto")
            self.classic_scale_mode_combo.setCurrentText("top_db")
            self.classic_p_lo_spin.setValue(1.0)
            self.classic_p_hi_spin.setValue(99.0)
            self.classic_n_mels_hue_spin.setValue(128)
            self.classic_n_mels_layers_spin.setValue(64)
            self.classic_norm_p_spin.setValue(99.5)
            self.classic_fuse7_profile_combo.setCurrentText("ref_compat")
            self.classic_flux_gain_spin.setValue(110.0)
            self.classic_edge_gain_spin.setValue(70.0)
            self.classic_freq_green_bias_spin.setValue(0.15)
            self.classic_edge_base_alpha_spin.setValue(0.25)
        elif preset == "classic_impulse":
            self.classic_n_fft_spin.setValue(4096)
            self.classic_win_ms_spin.setValue(20.0)
            self.classic_hop_ms_spin.setValue(0.25)
            self.classic_top_db_spin.setValue(80.0)
            self.classic_fmax_spin.setValue(24000.0)
            self.classic_detail_mode_combo.setCurrentText("off")
            self.classic_detail_sigma_spin.setValue(1.2)
            self.classic_detail_gain_spin.setValue(70.0)
            self.classic_detail_p_spin.setValue(99.5)
            self.classic_freq_interp_combo.setCurrentText("auto")
            self.classic_scale_mode_combo.setCurrentText("top_db")
            self.classic_p_lo_spin.setValue(1.0)
            self.classic_p_hi_spin.setValue(99.0)
            self.classic_n_mels_hue_spin.setValue(128)
            self.classic_n_mels_layers_spin.setValue(64)
            self.classic_norm_p_spin.setValue(99.5)
            self.classic_fuse7_profile_combo.setCurrentText("ref_compat")
            self.classic_flux_gain_spin.setValue(110.0)
            self.classic_edge_gain_spin.setValue(70.0)
            self.classic_freq_green_bias_spin.setValue(0.15)
            self.classic_edge_base_alpha_spin.setValue(0.25)
        self._update_classic_style_ui()
        self._schedule_sound_preview_reconfigure()

    def _update_sound_formula_labels(self) -> None:
        self._update_classic_style_ui()
        fps = max(1e-6, float(self.audio_fps_spin.value()))
        window_sec = max(1e-6, float(self.audio_window_spin.value()))
        interval = 1.0 / fps
        fps_max = 1.0 / window_sec
        self.audio_fps_info_label.setText(
            f"interval = 1/FPS = {interval:.3f}s | FPS max (bez overlapu) = 1/window = {fps_max:.3f}"
        )

        overlap_sec = max(0.0, window_sec - interval)
        overlap_pct = (100.0 * overlap_sec / window_sec) if window_sec > 0 else 0.0
        gap_sec = max(0.0, interval - window_sec)
        if overlap_sec > 0:
            self.classic_overlap_info_label.setText(
                f"Stride {interval:.3f} s | Overlap {overlap_sec:.3f} s ({overlap_pct:.1f} %)"
            )
        else:
            self.classic_overlap_info_label.setText(
                f"Stride {interval:.3f} s | Gap {gap_sec:.3f} s (bez overlapu)"
            )

        frame_seconds = float(self.payload_frame_seconds_spin.value())
        overlap = float(self.payload_overlap_combo.currentData() or 50.0)
        width_px = max(1, int(round(frame_seconds * 1000.0)))
        hop_samples = max(1, int(round(96.0 * (1.0 - overlap / 100.0))))
        required_samples = 96 + max(0, width_px - 1) * hop_samples
        covered_audio_sec = required_samples / 96000.0
        self.payload_formula_label.setText(
            "width_px=round(frame_seconds*1000), "
            f"hop_samples=round(96*(1-overlap/100))={hop_samples}, "
            f"required_samples={required_samples}, covered_audio_sec={covered_audio_sec:.4f}s"
        )

    def _classic_dependency_issue_message(self, cfg: AppConfig) -> str | None:
        if not cfg.audio.enabled or str(cfg.audio.approach).strip().lower() != "classic":
            return None
        deps = classic_dependencies_status()
        if bool(deps.get("scipy_available", False)):
            return None
        python_exe = sys.executable or r"C:\Users\P_J\AppData\Local\Programs\Python\Python313\python.exe"
        install_cmd = f'"{python_exe}" -m pip install "scipy>=1.10"'
        return (
            "Classic režim vyžaduje knihovnu scipy>=1.10.\n"
            f"Použitý Python: {python_exe}\n"
            f"Nainstalujte: {install_cmd}"
        )

    def _ensure_sound_preview_dialog(self) -> SoundCameraPreviewDialog:
        if self.sound_preview_dialog is None:
            self.sound_preview_dialog = SoundCameraPreviewDialog(self)
            self.sound_preview_dialog.set_snapshot_callback(self._save_preview_snapshot)
        return self.sound_preview_dialog

    def _open_sound_preview_dialog(self) -> None:
        dialog = self._ensure_sound_preview_dialog()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _start_sound_preview(self) -> None:
        if self.state.runner and self.state.runner.get_status() != "stopped":
            QtWidgets.QMessageBox.warning(
                self,
                "Preview",
                "Nezávislý preview nelze spustit během aktivního odesílání.",
            )
            return
        try:
            cfg = self._gather_config()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Preview", f"Nastavení není validní: {exc}")
            return
        dep_issue = self._classic_dependency_issue_message(cfg)
        if dep_issue:
            self.audio_device_status_label.setText("Classic preview zablokován: chybí scipy.")
            QtWidgets.QMessageBox.warning(self, "Preview", dep_issue)
            return
        if self.sound_preview_controller is None:
            logger = setup_logging(cfg.logging)
            self.sound_preview_controller = SoundCameraPreviewController(logger=logger)
        if not self.sound_preview_controller.is_running():
            self.sound_preview_controller.start(cfg)
        self._open_sound_preview_dialog()
        self._update_sound_preview_buttons()

    def _stop_sound_preview(self) -> None:
        self.sound_preview_reconfig_timer.stop()
        if self.sound_preview_controller is not None:
            self.sound_preview_controller.stop()
        self._update_sound_preview_buttons()

    def _update_sound_preview_buttons(self) -> None:
        running = bool(self.sound_preview_controller and self.sound_preview_controller.is_running())
        self.audio_preview_start_btn.setEnabled(not running)
        self.audio_preview_stop_btn.setEnabled(running)

    def _save_preview_snapshot(self) -> None:
        dialog = self._ensure_sound_preview_dialog()
        image = dialog.latest_image()
        if image.size == 0:
            return
        snapshot_dir = Path(self.audio_snapshot_dir_edit.text().strip() or "sound_camera_snapshots").expanduser()
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        prefix = self.audio_file_prefix_edit.text().strip() or "sound"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        out_path = snapshot_dir / f"{prefix}_preview_{stamp}.png"
        cv2.imwrite(str(out_path), image)
        self.audio_device_status_label.setText(f"Snapshot ulozen: {out_path.name}")

    def _poll_sound_preview_sources(self) -> None:
        latest: SoundCameraFrame | None = None
        if self.sound_preview_controller and self.sound_preview_controller.is_running():
            latest = self.sound_preview_controller.poll_latest()
        while True:
            try:
                latest = self.sound_preview_queue.get_nowait()
            except queue.Empty:
                break

        if latest is None:
            self._update_sound_preview_buttons()
            return

        dialog = self._ensure_sound_preview_dialog()
        meta = latest.meta or {}
        status = (
            f"{latest.approach} | src={latest.source} | "
            f"{meta.get('width_px', '?')}x{meta.get('height_px', '?')}"
        )
        meta_text = ", ".join(
            [
                f"{k}={v}"
                for k, v in meta.items()
                if k in {"frame_seconds", "tau", "preset", "style", "axis_mode"}
            ]
        )
        dialog.update_frame(latest.image_bgr, status_text=status, meta_text=meta_text)
        self._update_sound_preview_buttons()

    def _on_runner_sound_preview_frame(self, frame: SoundCameraFrame) -> None:
        while True:
            try:
                self.sound_preview_queue.put_nowait(frame)
                return
            except queue.Full:
                try:
                    self.sound_preview_queue.get_nowait()
                except queue.Empty:
                    return

    def _build_pekat_info_tab(self) -> None:
        _, layout = self._build_scroll_tab_root(self.pekat_info_tab)

        common_group = QtWidgets.QGroupBox("Common PEKAT ports")
        common_layout = QtWidgets.QVBoxLayout(common_group)
        self._apply_compact_box_layout(common_layout)
        self.common_ports_table = QtWidgets.QTableWidget(0, 5)
        self.common_ports_table.setHorizontalHeaderLabels(
            ["Port / Range", "Purpose", "Link", "Last status", "Owner classification"]
        )
        self.common_ports_table.verticalHeader().setVisible(False)
        self.common_ports_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.common_ports_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.common_ports_table.horizontalHeader().setStretchLastSection(True)
        common_layout.addWidget(self.common_ports_table)
        layout.addWidget(common_group, 0)

        scan_group = QtWidgets.QGroupBox("Port status check")
        scan_layout = QtWidgets.QVBoxLayout(scan_group)
        self._apply_compact_box_layout(scan_layout)
        controls_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(controls_layout)
        self.check_common_ports_btn = QtWidgets.QPushButton("Check common ports")
        self.scan_range_btn = QtWidgets.QPushButton("Scan range 8000-8100")
        self.port_scan_status_label = QtWidgets.QLabel("Idle")
        controls_layout.addWidget(self.check_common_ports_btn)
        controls_layout.addWidget(self.scan_range_btn)
        controls_layout.addWidget(self.port_scan_status_label)
        controls_layout.addStretch(1)
        scan_layout.addLayout(controls_layout)

        self.port_scan_table = QtWidgets.QTableWidget(0, 6)
        self.port_scan_table.setHorizontalHeaderLabels(
            ["Port", "Listening", "PID", "Process", "Allocated by", "Detail"]
        )
        self.port_scan_table.verticalHeader().setVisible(False)
        self.port_scan_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.port_scan_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.port_scan_table.horizontalHeader().setStretchLastSection(True)
        scan_layout.addWidget(self.port_scan_table)
        layout.addWidget(scan_group, 0)

        links_group = QtWidgets.QGroupBox("Useful links")
        links_layout = QtWidgets.QFormLayout(links_group)
        self._apply_compact_form_layout(links_layout)
        links_layout.addRow(
            "PEKAT homepage",
            self._make_link_label("https://www.pekatvision.com"),
        )
        links_layout.addRow(
            "PEKAT KB 3.19 Home",
            self._make_link_label(
                "https://pekatvision.atlassian.net/wiki/spaces/KB34/pages/1207107616/PEKAT+VISION+Knowledge+base+3.19+Home"
            ),
        )
        links_layout.addRow(
            "PEKAT GitHub",
            self._make_link_label("https://github.com/pekat-vision"),
        )
        layout.addWidget(links_group, 0)

        network_group = QtWidgets.QGroupBox()
        network_group.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
        )
        network_layout = QtWidgets.QVBoxLayout(network_group)
        self._apply_compact_box_layout(network_layout)
        network_header_layout = QtWidgets.QHBoxLayout()
        self._apply_compact_box_layout(network_header_layout)
        network_title_label = QtWidgets.QLabel("PC network settings")
        title_font = network_title_label.font()
        title_font.setBold(True)
        network_title_label.setFont(title_font)
        self.network_info_status_label = QtWidgets.QLabel("Status: not loaded")
        self.network_info_status_label.setStyleSheet("color: #666;")
        network_header_layout.addWidget(network_title_label)
        network_header_layout.addStretch(1)
        network_header_layout.addWidget(self.network_info_status_label)

        self.network_cards_scroll = QtWidgets.QScrollArea()
        self.network_cards_scroll.setWidgetResizable(True)
        self.network_cards_container = QtWidgets.QWidget()
        self.network_cards_layout = QtWidgets.QGridLayout(self.network_cards_container)
        self.network_cards_layout.setContentsMargins(6, 6, 6, 6)
        self.network_cards_layout.setHorizontalSpacing(10)
        self.network_cards_layout.setVerticalSpacing(6)
        self.network_cards_scroll.setWidget(self.network_cards_container)

        network_layout.addLayout(network_header_layout)
        network_layout.addWidget(self.network_cards_scroll)
        layout.addWidget(network_group, 1)

        self.check_common_ports_btn.clicked.connect(self._check_common_ports)
        self.scan_range_btn.clicked.connect(self._scan_range_ports)
        self._populate_known_ports_table()

    @staticmethod
    def _make_link_label(url: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(f"<a href='{url}'>{url}</a>")
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        return label

    @staticmethod
    def _set_table_item(table: QtWidgets.QTableWidget, row: int, col: int, value: str) -> None:
        item = QtWidgets.QTableWidgetItem(value)
        table.setItem(row, col, item)

    def _populate_known_ports_table(self) -> None:
        self.known_port_entries = get_known_pekat_ports()
        self.known_port_row_map = {}
        self.common_ports_table.setRowCount(len(self.known_port_entries))

        for row, entry in enumerate(self.known_port_entries):
            self.known_port_row_map.setdefault(entry.port, []).append(row)
            self._set_table_item(self.common_ports_table, row, 0, entry.port)
            self._set_table_item(self.common_ports_table, row, 1, entry.purpose)
            link_label = self._make_link_label(entry.link)
            self.common_ports_table.setCellWidget(row, 2, link_label)
            self._set_table_item(self.common_ports_table, row, 3, "-")
            self._set_table_item(self.common_ports_table, row, 4, "-")

        self.common_ports_table.resizeColumnsToContents()

    def _set_known_port_status(self, key: str, status: str, owner: str) -> None:
        rows = self.known_port_row_map.get(key, [])
        if not rows:
            return
        for row in rows:
            self._set_table_item(self.common_ports_table, row, 3, status)
            self._set_table_item(self.common_ports_table, row, 4, owner)

    def _check_common_ports(self) -> None:
        if self.port_scan_running:
            return
        self.port_scan_running = True
        self.check_common_ports_btn.setEnabled(False)
        self.scan_range_btn.setEnabled(False)
        self.port_scan_status_label.setText("Scanning common ports...")

        def worker() -> None:
            try:
                results = check_ports([7000, 7002, 8000, 1947], include_closed=True)
                range_results = scan_port_range(8000, 8100)
                self._post_to_ui(lambda: self._apply_common_scan_results(results, range_results))
            except Exception as exc:
                self._post_to_ui(
                    lambda message=str(exc): self.port_scan_status_label.setText(f"Error: {message}")
                )
            finally:
                self._post_to_ui(self._finish_port_scan)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_range_ports(self) -> None:
        if self.port_scan_running:
            return
        self.port_scan_running = True
        self.check_common_ports_btn.setEnabled(False)
        self.scan_range_btn.setEnabled(False)
        self.port_scan_status_label.setText("Scanning range 8000-8100...")

        def worker() -> None:
            try:
                results = scan_port_range(8000, 8100)
                self._post_to_ui(lambda: self._fill_scan_table(results))
                occupied = len(results)
                self._post_to_ui(
                    lambda: self._set_known_port_status(
                        "8000-8100",
                        f"Occupied: {occupied}",
                        "Use table below for details",
                    )
                )
                self._post_to_ui(lambda: self.port_scan_status_label.setText("Done"))
            except Exception as exc:
                self._post_to_ui(
                    lambda message=str(exc): self.port_scan_status_label.setText(f"Error: {message}")
                )
            finally:
                self._post_to_ui(self._finish_port_scan)

        threading.Thread(target=worker, daemon=True).start()

    def _post_to_ui(self, callback) -> None:
        self.ui_callback_signal.emit(callback)

    def _finish_port_scan(self) -> None:
        self.port_scan_running = False
        self.check_common_ports_btn.setEnabled(True)
        self.scan_range_btn.setEnabled(True)
        if self.port_scan_status_label.text().startswith("Scanning"):
            self.port_scan_status_label.setText("Done")

    def _apply_common_scan_results(
        self, results: List[PortScanResult], range_results: List[PortScanResult]
    ) -> None:
        result_map = {result.port: result for result in results}
        for port in [7000, 7002, 8000, 1947]:
            result = result_map.get(port)
            if result is None:
                self._set_known_port_status(str(port), "No data", "Unknown")
                continue
            if result.listening:
                status = f"Listening (PID {result.pid or '-'})"
            else:
                status = "Closed"
            self._set_known_port_status(str(port), status, result.allocated_by)

        occupied = len(range_results)
        self._set_known_port_status(
            "8000-8100",
            f"Occupied: {occupied}",
            "Use table below for details",
        )

        self._fill_scan_table(results + range_results)
        self.port_scan_status_label.setText("Done")

    def _fill_scan_table(self, results: List[PortScanResult]) -> None:
        unique_results: Dict[int, PortScanResult] = {}
        for result in results:
            unique_results[result.port] = result
        rows = sorted(unique_results.values(), key=lambda item: item.port)

        self.port_scan_table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            self._set_table_item(self.port_scan_table, row_idx, 0, str(item.port))
            self._set_table_item(
                self.port_scan_table, row_idx, 1, "Yes" if item.listening else "No"
            )
            self._set_table_item(
                self.port_scan_table,
                row_idx,
                2,
                "" if item.pid is None else str(item.pid),
            )
            self._set_table_item(self.port_scan_table, row_idx, 3, item.process_name or "-")
            self._set_table_item(self.port_scan_table, row_idx, 4, item.allocated_by)
            self._set_table_item(self.port_scan_table, row_idx, 5, item.detail)

        self.port_scan_table.resizeColumnsToContents()

    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.pekat_info_tab:
            self._load_network_info()

    def _load_network_info(self) -> None:
        if self.network_info_loading:
            return
        self.network_info_loading = True
        self.network_info_status_label.setText("Status: loading...")

        def worker() -> None:
            try:
                adapters = get_network_adapters_info()
                self._post_to_ui(lambda payload=adapters: self._render_network_adapters(payload))
                self._post_to_ui(
                    lambda: self.network_info_status_label.setText("Status: loaded")
                )
            except Exception as exc:
                self._post_to_ui(
                    lambda message=str(exc): self.network_info_status_label.setText(
                        f"Status: error ({message})"
                    )
                )
            finally:
                self._post_to_ui(self._finish_network_info_load)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_network_info_load(self) -> None:
        self.network_info_loading = False

    @staticmethod
    def _adapter_priority(adapter_name: str) -> int:
        lowered = (adapter_name or "").lower()
        if "bluetooth" in lowered:
            return 2
        if "wi-fi" in lowered or "wifi" in lowered or "wireless" in lowered or "wlan" in lowered:
            return 1
        return 0

    def _clear_network_cards(self) -> None:
        while self.network_cards_layout.count():
            item = self.network_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_network_adapters(self, adapters: List[NetworkAdapterInfo]) -> None:
        self._clear_network_cards()
        if not adapters:
            label = QtWidgets.QLabel("No adapter data available.")
            self.network_cards_layout.addWidget(label, 0, 0)
            return

        sorted_adapters = sorted(
            adapters,
            key=lambda item: (self._adapter_priority(item.adapter_name), item.adapter_name.lower()),
        )

        for idx, adapter in enumerate(sorted_adapters):
            card = QtWidgets.QGroupBox(adapter.adapter_name or "Unknown adapter")
            card_layout = QtWidgets.QFormLayout(card)
            self._apply_compact_form_layout(card_layout)
            network_label = QtWidgets.QLabel(adapter.network_name or "-")
            mac_label = QtWidgets.QLabel(adapter.mac_address or "-")
            ipv4_label = QtWidgets.QLabel("\n".join(adapter.ipv4_with_masks or ["- / -"]))
            ipv4_label.setWordWrap(True)
            card_layout.addRow("Network", network_label)
            card_layout.addRow("MAC", mac_label)
            card_layout.addRow("IPv4/Subnet", ipv4_label)

            row = idx // 2
            col = idx % 2
            self.network_cards_layout.addWidget(card, row, col)

        self.network_cards_layout.setColumnStretch(0, 1)
        self.network_cards_layout.setColumnStretch(1, 1)

    def _select_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Vyberte složku")
        if folder:
            self.folder_edit.setText(folder)
            self.selected_files = []
            self.files_label.setText("0 souborů")

    def _select_files(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Vyberte soubory")
        if files:
            self.selected_files = files
            self.files_label.setText(f"{len(files)} souborů")

    def _gather_config(self) -> AppConfig:
        # Build runtime config from current GUI form state.
        cfg = AppConfig()
        cfg.mode = self.mode_combo.currentText()
        cfg.host = self.host_edit.text().strip() or "127.0.0.1"
        cfg.port = int(self.port_spin.value())
        cfg.project_path = self.project_path_edit.text().strip()
        cfg.input.folder = self.folder_edit.text().strip()
        cfg.input.include_subfolders = self.include_subfolders_check.isChecked()
        if self.selected_files:
            cfg.input.source_type = "files"
            cfg.input.files = self.selected_files
        else:
            cfg.input.source_type = "folder"

        cfg.behavior.run_mode = str(self.run_mode_combo.currentData() or "initial_then_watch")
        cfg.behavior.delay_between_images_ms = int(self.delay_spin.value())
        sound_send_mode = str(self.audio_send_mode_combo.currentData() or "save_send")
        sound_send_only = self.audio_enable_check.isChecked() and sound_send_mode == "send_only"
        cfg.file_actions.enabled = bool(
            self.file_actions_enable_check.isChecked()
            and self.file_actions_enable_check.isEnabled()
            and not sound_send_only
        )
        cfg.file_actions.mode = str(self.file_actions_mode_combo.currentData() or "move_by_result")
        cfg.file_actions.save_json_context = self.file_actions_save_json_check.isChecked()
        cfg.file_actions.save_processed_image = self.file_actions_save_processed_check.isChecked()
        cfg.file_actions.processed_response_type = "annotated_image"
        cfg.file_actions.ok.base_dir = self.file_ok_dir_edit.text().strip()
        cfg.file_actions.ok.create_daily_folder = self.file_ok_daily_check.isChecked()
        cfg.file_actions.ok.create_hourly_folder = self.file_ok_hourly_check.isChecked()
        cfg.file_actions.ok.include_result_prefix = self.file_ok_result_check.isChecked()
        cfg.file_actions.ok.include_timestamp_suffix = self.file_ok_timestamp_check.isChecked()
        cfg.file_actions.ok.include_string = self.file_ok_string_check.isChecked()
        cfg.file_actions.ok.string_value = self.file_ok_string_edit.text()
        cfg.file_actions.nok.base_dir = self.file_nok_dir_edit.text().strip()
        cfg.file_actions.nok.create_daily_folder = self.file_nok_daily_check.isChecked()
        cfg.file_actions.nok.create_hourly_folder = self.file_nok_hourly_check.isChecked()
        cfg.file_actions.nok.include_result_prefix = self.file_nok_result_check.isChecked()
        cfg.file_actions.nok.include_timestamp_suffix = self.file_nok_timestamp_check.isChecked()
        cfg.file_actions.nok.include_string = self.file_nok_string_check.isChecked()
        cfg.file_actions.nok.string_value = self.file_nok_string_edit.text()
        cfg.pekat.data_include_filename = self.data_filename_check.isChecked()
        cfg.pekat.data_include_timestamp = self.data_timestamp_check.isChecked()
        cfg.pekat.data_include_string = self.data_string_check.isChecked()
        cfg.pekat.data_string_value = self.data_string_edit.text()

        cfg.rest.api_key = self.api_key_value
        cfg.rest.api_key_location = self.api_key_location_value
        cfg.rest.api_key_name = self.api_key_name_value or "api_key"

        cfg.connection.policy = self.pm_policy_combo.currentData()
        cfg.projects_manager.tcp_enabled = self.pm_tcp_enabled_check.isChecked()
        cfg.projects_manager.tcp_host = self.pm_tcp_host_edit.text().strip() or "127.0.0.1"
        cfg.projects_manager.tcp_port = int(self.pm_tcp_port_spin.value())
        cfg.audio.enabled = self.audio_enable_check.isChecked()
        cfg.audio.backend = "sounddevice"  # legacy compatibility field
        cfg.audio.source_mode = "audio_only"
        cfg.audio.approach = str(self.audio_approach_combo.currentData() or "payload")
        cfg.audio.source = str(self.audio_source_combo.currentData() or "loopback")
        cfg.audio.backend_policy = str(self.audio_backend_policy_combo.currentData() or "auto")
        cfg.audio.send_mode = sound_send_mode
        cfg.audio.device_name = str(self.audio_device_combo.currentData() or "")
        cfg.audio.sample_rate_hz = int(self.audio_sample_rate_spin.value())
        cfg.audio.channels = 2 if cfg.audio.source == "loopback" else 1
        cfg.audio.window_sec = float(self.audio_window_spin.value())
        fps = max(1e-6, float(self.audio_fps_spin.value()))
        cfg.audio.interval_sec = 1.0 / fps
        cfg.audio.snapshot_dir = self.audio_snapshot_dir_edit.text().strip()
        cfg.audio.file_prefix = self.audio_file_prefix_edit.text().strip() or "sound"
        cfg.audio.sine_freq_hz = float(self.audio_sine_freq_spin.value())

        cfg.audio.payload.frame_seconds = float(self.payload_frame_seconds_spin.value())
        cfg.audio.payload.overlap_percent = float(self.payload_overlap_combo.currentData() or 50.0)
        cfg.audio.payload.style_mode = str(self.payload_style_combo.currentData() or "stack3")
        cfg.audio.payload.y_repeat = int(self.payload_y_repeat_combo.currentData() or 4)
        cfg.audio.payload.variant_mode = str(self.payload_variant_combo.currentData() or "none")
        cfg.audio.payload.preview_resize_mode = str(
            self.payload_preview_resize_combo.currentData() or "pixel"
        )
        cfg.audio.payload.overlay_grid = self.payload_overlay_grid_check.isChecked()
        cfg.audio.payload.overlay_time_ticks = self.payload_overlay_time_check.isChecked()
        cfg.audio.payload.overlay_stack_bounds = self.payload_overlay_stack_check.isChecked()
        cfg.audio.payload.overlay_legend = self.payload_overlay_legend_check.isChecked()

        tau_value = self.liss_tau_combo.currentData()
        if str(tau_value) == "both":
            cfg.audio.lissajous.tau = "both"
        else:
            cfg.audio.lissajous.tau = int(tau_value or 5)
        cfg.audio.lissajous.width = int(self.liss_width_spin.value())
        cfg.audio.lissajous.height = int(self.liss_height_spin.value())
        cfg.audio.lissajous.accum = str(self.liss_accum_combo.currentData() or "none")
        cfg.audio.lissajous.point_size_step = int(self.liss_point_size_spin.value())
        cfg.audio.lissajous.point_render_style = str(
            self.liss_point_style_combo.currentData() or "classic"
        )
        cfg.audio.lissajous.value_mode = str(self.liss_value_mode_combo.currentData() or "radial")
        cfg.audio.lissajous.rotation = str(self.liss_rotation_combo.currentData() or "none")

        cfg.audio.classic.preset = str(self.classic_preset_combo.currentData() or "none")
        cfg.audio.classic.style = str(self.classic_style_combo.currentData() or "classic")
        cfg.audio.classic.axis_mode = str(self.classic_axis_combo.currentData() or "linear")
        cfg.audio.classic.scale_mode = str(self.classic_scale_mode_combo.currentData() or "top_db")
        cfg.audio.classic.p_lo = float(self.classic_p_lo_spin.value())
        cfg.audio.classic.p_hi = float(self.classic_p_hi_spin.value())
        cfg.audio.classic.n_mels_hue = int(self.classic_n_mels_hue_spin.value())
        cfg.audio.classic.n_mels_layers = int(self.classic_n_mels_layers_spin.value())
        cfg.audio.classic.fuse7_profile = str(self.classic_fuse7_profile_combo.currentData() or "ref_compat")
        cfg.audio.classic.norm_p = float(self.classic_norm_p_spin.value())
        cfg.audio.classic.freq_green_bias = float(self.classic_freq_green_bias_spin.value())
        cfg.audio.classic.edge_base_alpha = float(self.classic_edge_base_alpha_spin.value())
        cfg.audio.classic.flux_gain = float(self.classic_flux_gain_spin.value())
        cfg.audio.classic.edge_gain = float(self.classic_edge_gain_spin.value())
        cfg.audio.classic.width = int(self.classic_width_spin.value())
        cfg.audio.classic.height = int(self.classic_height_spin.value())
        cfg.audio.classic.n_fft = int(self.classic_n_fft_spin.value())
        cfg.audio.classic.win_ms = float(self.classic_win_ms_spin.value())
        cfg.audio.classic.hop_ms = float(self.classic_hop_ms_spin.value())
        cfg.audio.classic.top_db = float(self.classic_top_db_spin.value())
        cfg.audio.classic.fmax = float(self.classic_fmax_spin.value())
        cfg.audio.classic.colormap = str(self.classic_colormap_combo.currentData() or "gray")
        cfg.audio.classic.gamma = float(self.classic_gamma_spin.value())
        cfg.audio.classic.detail_mode = str(self.classic_detail_mode_combo.currentData() or "off")
        cfg.audio.classic.detail_sigma = float(self.classic_detail_sigma_spin.value())
        cfg.audio.classic.detail_gain = float(self.classic_detail_gain_spin.value())
        cfg.audio.classic.detail_p = float(self.classic_detail_p_spin.value())
        cfg.audio.classic.freq_interp = str(self.classic_freq_interp_combo.currentData() or "auto")
        if cfg.audio.classic.hop_ms > cfg.audio.classic.win_ms:
            raise ValueError("Classic: Hop ms musi byt <= Win ms.")
        if cfg.audio.classic.style == "classic" and cfg.audio.classic.axis_mode == "log" and cfg.audio.classic.fmax <= 20.0:
            raise ValueError("Classic: Osa Y=log vyzaduje Fmax > 20 Hz.")

        return cfg

    def _connect(self) -> None:
        cfg = self._gather_config()
        self._save_gui_settings()
        logger = setup_logging(cfg.logging)
        logger.addHandler(self.qt_handler)
        if self.state.connection is None:
            connection = ConnectionManager(cfg, logger)
            self.state.connection = connection
        else:
            connection = self.state.connection
            connection.update_config(cfg)
        self.state.config = cfg

        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.connection_label.setText("connecting")
        self.timer.start()

        def _connect_worker() -> None:
            ok = connection.connect()
            if not ok:
                self.connection_label.setText("error")

        threading.Thread(target=_connect_worker, daemon=True).start()

    def _disconnect(self) -> None:
        if self.state.runner:
            self._stop()
        if not self.state.connection:
            return
        self.connection_label.setText("disconnecting")

        def _disconnect_worker() -> None:
            if self.state.connection:
                self.state.connection.disconnect()

        threading.Thread(target=_disconnect_worker, daemon=True).start()

    def _start(self) -> None:
        if not self.state.connection or not self.state.connection.is_connected():
            QtWidgets.QMessageBox.warning(self, "Not connected", "Nejprve se připojte k projektu.")
            return
        try:
            cfg = self._gather_config()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Configuration error", str(exc))
            return
        if cfg.audio.enabled:
            if cfg.audio.approach != "classic" and cfg.audio.interval_sec < cfg.audio.window_sec:
                fps = 1.0 / max(cfg.audio.interval_sec, 1e-9)
                fps_max = 1.0 / max(cfg.audio.window_sec, 1e-9)
                QtWidgets.QMessageBox.warning(
                    self,
                    "Sound camera",
                    f"FPS je příliš vysoké pro zvolenou délku okna. "
                    f"Nastaveno {fps:.3f} FPS, maximum je {fps_max:.3f} FPS.",
                )
                return
            dep_issue = self._classic_dependency_issue_message(cfg)
            if dep_issue:
                self.audio_device_status_label.setText("Classic odesílání zablokováno: chybí scipy.")
                QtWidgets.QMessageBox.warning(self, "Sound camera", dep_issue)
                return
            if cfg.audio.send_mode == "save_send":
                snapshot_dir_raw = cfg.audio.snapshot_dir.strip()
                if not snapshot_dir_raw:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Sound camera",
                        "V režimu Save+Send musíte vyplnit Snapshot složku.",
                    )
                    return
                snapshot_dir = Path(snapshot_dir_raw).expanduser()
                try:
                    snapshot_dir.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Sound camera",
                        f"Snapshot složku nelze vytvořit: {exc}",
                    )
                    return
                if not snapshot_dir.is_dir():
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Sound camera",
                        "Snapshot složka není platný adresář.",
                    )
                    return

        if self.sound_preview_controller and self.sound_preview_controller.is_running():
            self.sound_preview_controller.stop()
        while True:
            try:
                self.sound_preview_queue.get_nowait()
            except queue.Empty:
                break

        self.state.config = cfg
        logger = self.state.connection.logger if self.state.connection else setup_logging(cfg.logging)
        logger.addHandler(self.qt_handler)
        runner = Runner(cfg, self.state.connection, logger)
        runner.set_preview_callback(self._on_runner_sound_preview_frame)
        try:
            runner.start()
        except Exception as exc:
            runner.set_preview_callback(None)
            QtWidgets.QMessageBox.warning(self, "Start failed", f"Start odesílání selhal: {exc}")
            return

        self.stop_requested = False
        self.stop_start_time = None
        self.state.runner = runner
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.timer.start()
        self._update_sound_preview_buttons()

    def _stop(self) -> None:
        runner = self.state.runner
        if not runner:
            return
        runner.set_preview_callback(None)
        self.stop_requested = True
        self.stop_start_time = time.time()
        self.stop_btn.setEnabled(False)
        self.send_status_label.setText("stopping")

        def _stop_worker() -> None:
            runner.stop()

        threading.Thread(target=_stop_worker, daemon=True).start()

    def _update_status(self) -> None:
        # UI refresh tick driven by timer.
        connection = self.state.connection
        runner = self.state.runner

        if connection:
            cfg = self.state.config
            if (
                cfg
                and connection.state not in {"connecting", "disconnecting"}
                and time.time() - self.last_ping_time >= cfg.pekat.health_ping_sec
            ):
                if not self.health_check_inflight:
                    self.health_check_inflight = True

                    def _health_worker() -> None:
                        try:
                            connection.check_health()
                        finally:
                            self.health_check_inflight = False

                    threading.Thread(target=_health_worker, daemon=True).start()
                    self.last_ping_time = time.time()
            self.connection_label.setText(connection.status_text)
            if connection.last_production_mode is True:
                self.production_label.setText("Production Mode ON")
            elif connection.last_production_mode is False:
                self.production_label.setText("Production Mode OFF")
            else:
                self.production_label.setText("Production Mode: Unknown")
            self.data_preview_label.setText(connection.last_data)
            if connection.last_eval_time_ms is None:
                self.last_eval_time_label.setText("-")
            else:
                self.last_eval_time_label.setText(str(connection.last_eval_time_ms))
            if connection.avg_eval_time_ms is None:
                self.avg_eval_time_label.setText("-")
            else:
                self.avg_eval_time_label.setText(f"{connection.avg_eval_time_ms:.1f}")
            self.nok_count_value.setText(str(connection.nok_count))
            self.ok_count_value.setText(str(connection.ok_count))
            self.json_view.setPlainText(connection.last_result_json or "{}")
        else:
            self.connection_label.setText("disconnected")
            self.production_label.setText("Production Mode: Unknown")
            self.data_preview_label.setText("")
            self.count_label.setText("0")
            self.last_eval_time_label.setText("-")
            self.avg_eval_time_label.setText("-")
            self.nok_count_value.setText("0")
            self.ok_count_value.setText("0")
            self.json_view.setPlainText("{}")

        if not runner:
            self.send_status_label.setText("stopped")
        else:
            if self.stop_requested:
                elapsed = int(time.time() - (self.stop_start_time or time.time()))
                self.send_status_label.setText(f"stopping ({elapsed}s)")
            else:
                self.send_status_label.setText(runner.get_status())
            self.count_label.setText(str(runner.get_count()))
            if runner.get_status() == "stopped":
                runner.set_preview_callback(None)
                self.start_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                self.stop_requested = False

        if connection:
            self.count_label.setText(str(connection.total_sent))

        self._sync_controls()

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)

    def _reset_counters(self) -> None:
        if self.state.connection:
            self.state.connection.reset_counters()
        self.count_label.setText("0")
        self.last_eval_time_label.setText("-")
        self.avg_eval_time_label.setText("-")
        self.nok_count_value.setText("0")
        self.ok_count_value.setText("0")
        self.data_preview_label.setText("")
        self.json_view.setPlainText("{}")

    def _update_pm_controls(self) -> None:
        has_path = bool(self.project_path_edit.text().strip())
        tcp_enabled = self.pm_tcp_enabled_check.isChecked()
        enable_policy = tcp_enabled and has_path
        self.pm_policy_combo.setEnabled(enable_policy)
        if not enable_policy:
            self.pm_policy_combo.setCurrentIndex(0)
        if not tcp_enabled:
            self.pm_note_label.setText(
                "Funguje pouze pokud je TCP server v Projects Manageru aktivní."
            )
        elif not has_path:
            self.pm_note_label.setText("Vyplňte Project path pro TCP ovládání.")
        else:
            self.pm_note_label.setText("")

    def _sync_controls(self) -> None:
        # Enable/disable widgets based on connection and sender states.
        connection = self.state.connection
        runner = self.state.runner
        connected = bool(connection and connection.is_connected())
        connecting = bool(connection and connection.state in {"connecting", "reconnecting"})
        sending = bool(runner and runner.get_status() != "stopped")

        self.connect_btn.setEnabled(not connected and not connecting)
        self.disconnect_btn.setEnabled(connected or connecting)
        self.start_btn.setEnabled(connected and not sending)
        self.stop_btn.setEnabled(sending)

        connection_widgets = [
            self.mode_combo,
            self.host_edit,
            self.port_spin,
            self.project_path_edit,
            self.pm_tcp_enabled_check,
            self.pm_tcp_host_edit,
            self.pm_tcp_port_spin,
            self.pm_policy_combo,
            self.api_key_button,
        ]
        sending_widgets = [
            self.folder_edit,
            self.include_subfolders_check,
            self.file_select_btn,
            self.run_mode_combo,
            self.delay_spin,
            self.file_actions_enable_check,
            self.file_actions_save_json_check,
            self.file_actions_save_processed_check,
            self.file_actions_mode_combo,
            self.file_ok_group,
            self.file_nok_group,
            self.data_filename_check,
            self.data_timestamp_check,
            self.data_string_check,
            self.data_string_edit,
            self.audio_enable_check,
            self.audio_approach_combo,
            self.audio_source_combo,
            self.audio_device_combo,
            self.audio_refresh_devices_btn,
            self.audio_backend_policy_combo,
            self.audio_send_mode_combo,
            self.audio_snapshot_dir_edit,
            self.audio_snapshot_dir_btn,
            self.audio_file_prefix_edit,
            self.audio_fps_spin,
            self.audio_window_spin,
            self.audio_sample_rate_spin,
            self.audio_sine_freq_spin,
            self.payload_frame_seconds_spin,
            self.payload_overlap_combo,
            self.payload_style_combo,
            self.payload_y_repeat_combo,
            self.payload_variant_combo,
            self.payload_preview_resize_combo,
            self.payload_overlay_grid_check,
            self.payload_overlay_time_check,
            self.payload_overlay_stack_check,
            self.payload_overlay_legend_check,
            self.liss_tau_combo,
            self.liss_width_spin,
            self.liss_height_spin,
            self.liss_accum_combo,
            self.liss_point_size_spin,
            self.liss_point_style_combo,
            self.liss_value_mode_combo,
            self.liss_rotation_combo,
            self.classic_preset_combo,
            self.classic_style_combo,
            self.classic_axis_combo,
            self.classic_width_spin,
            self.classic_height_spin,
            self.classic_n_fft_spin,
            self.classic_win_ms_spin,
            self.classic_hop_ms_spin,
            self.classic_top_db_spin,
            self.classic_fmax_spin,
            self.classic_colormap_combo,
            self.classic_gamma_spin,
            self.classic_detail_mode_combo,
            self.classic_detail_sigma_spin,
            self.classic_detail_gain_spin,
            self.classic_detail_p_spin,
            self.classic_freq_interp_combo,
            self.classic_fuse7_profile_combo,
            self.classic_scale_mode_combo,
            self.classic_p_lo_spin,
            self.classic_p_hi_spin,
            self.classic_n_mels_hue_spin,
            self.classic_n_mels_layers_spin,
            self.classic_norm_p_spin,
            self.classic_flux_gain_spin,
            self.classic_edge_gain_spin,
            self.classic_freq_green_bias_spin,
            self.classic_edge_base_alpha_spin,
            self.classic_advanced_btn,
            self.audio_preview_start_btn,
            self.audio_preview_stop_btn,
        ]

        for widget in connection_widgets:
            widget.setEnabled(not (connected or connecting))
        for widget in sending_widgets:
            widget.setEnabled(not sending)

        if not (connected or connecting):
            self._update_pm_controls()
            self._update_file_actions_loop_state()
        self._update_sound_send_mode_ui()
        self.data_string_edit.setEnabled(self.data_string_check.isChecked() and not sending)
        self._update_file_actions_string_edits()
        self._update_sound_preview_buttons()

    def _gui_config_path(self) -> Path:
        return Path.home() / ".pektool_gui.yaml"

    def _set_run_mode_combo(self, run_mode: str) -> None:
        for idx in range(self.run_mode_combo.count()):
            if self.run_mode_combo.itemData(idx) == run_mode:
                self.run_mode_combo.setCurrentIndex(idx)
                return
        self.run_mode_combo.setCurrentIndex(2)

    @staticmethod
    def _set_combo_data(combo: QtWidgets.QComboBox, value: object, fallback_index: int = 0) -> None:
        for idx in range(combo.count()):
            if combo.itemData(idx) == value:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(max(0, fallback_index))

    def _load_gui_settings(self) -> None:
        path = self._gui_config_path()
        if not path.exists():
            return
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return

        self.host_edit.setText(data.get("host", "127.0.0.1"))
        self.port_spin.setValue(int(data.get("port", 8000)))
        self.mode_combo.setCurrentText(str(data.get("mode", "rest")))
        self.project_path_edit.setText(data.get("project_path", ""))
        self.folder_edit.setText(data.get("folder", ""))
        self.include_subfolders_check.setChecked(bool(data.get("include_subfolders", True)))
        self._set_run_mode_combo(str(data.get("run_mode", "initial_then_watch")))
        self.delay_spin.setValue(int(data.get("delay_ms", 150)))
        self.file_actions_enable_check.setChecked(bool(data.get("file_actions_enabled", False)))
        self.file_actions_save_json_check.setChecked(bool(data.get("file_actions_save_json", False)))
        self.file_actions_save_processed_check.setChecked(bool(data.get("file_actions_save_processed", False)))
        file_mode = str(data.get("file_actions_mode", "move_by_result"))
        for idx in range(self.file_actions_mode_combo.count()):
            if self.file_actions_mode_combo.itemData(idx) == file_mode:
                self.file_actions_mode_combo.setCurrentIndex(idx)
                break
        self.file_ok_dir_edit.setText(data.get("file_ok_dir", ""))
        self.file_ok_daily_check.setChecked(bool(data.get("file_ok_daily", False)))
        self.file_ok_hourly_check.setChecked(bool(data.get("file_ok_hourly", False)))
        self.file_ok_result_check.setChecked(bool(data.get("file_ok_result_prefix", False)))
        self.file_ok_timestamp_check.setChecked(bool(data.get("file_ok_timestamp", False)))
        self.file_ok_string_check.setChecked(bool(data.get("file_ok_include_string", False)))
        self.file_ok_string_edit.setText(data.get("file_ok_string_value", ""))
        self.file_nok_dir_edit.setText(data.get("file_nok_dir", ""))
        self.file_nok_daily_check.setChecked(bool(data.get("file_nok_daily", False)))
        self.file_nok_hourly_check.setChecked(bool(data.get("file_nok_hourly", False)))
        self.file_nok_result_check.setChecked(bool(data.get("file_nok_result_prefix", False)))
        self.file_nok_timestamp_check.setChecked(bool(data.get("file_nok_timestamp", False)))
        self.file_nok_string_check.setChecked(bool(data.get("file_nok_include_string", False)))
        self.file_nok_string_edit.setText(data.get("file_nok_string_value", ""))
        self.data_filename_check.setChecked(bool(data.get("data_include_filename", True)))
        self.data_timestamp_check.setChecked(bool(data.get("data_include_timestamp", False)))
        self.data_string_check.setChecked(bool(data.get("data_include_string", False)))
        self.data_string_edit.setText(data.get("data_string_value", ""))
        self.data_string_edit.setEnabled(self.data_string_check.isChecked())
        self.audio_enable_check.setChecked(bool(data.get("sound_enabled", data.get("audio_enabled", False))))
        self._set_combo_data(
            self.audio_approach_combo,
            str(data.get("sound_approach", "payload")),
        )
        self._set_combo_data(
            self.audio_source_combo,
            str(data.get("sound_source", "loopback")),
        )
        self._set_combo_data(
            self.audio_backend_policy_combo,
            str(data.get("sound_backend_policy", "auto")),
        )
        self._set_combo_data(
            self.audio_send_mode_combo,
            str(data.get("sound_send_mode", "save_send")),
        )

        self.audio_snapshot_dir_edit.setText(
            str(data.get("sound_snapshot_dir", data.get("audio_snapshot_dir", "sound_camera_snapshots")))
        )
        loaded_fps = data.get("sound_fps")
        if loaded_fps is not None:
            self.audio_fps_spin.setValue(float(loaded_fps))
        else:
            interval_fallback = float(data.get("sound_interval_sec", data.get("audio_interval_sec", 2.0)))
            self.audio_fps_spin.setValue(1.0 / max(interval_fallback, 1e-6))
        self.audio_window_spin.setValue(
            float(data.get("sound_window_sec", data.get("audio_window_sec", 1.0)))
        )
        self.audio_sample_rate_spin.setValue(
            int(data.get("sound_sample_rate_hz", data.get("audio_sample_rate_hz", 16000)))
        )
        self.audio_sine_freq_spin.setValue(float(data.get("sound_sine_freq_hz", 440.0)))
        self.audio_file_prefix_edit.setText(str(data.get("sound_file_prefix", "sound")))
        self._refresh_audio_devices(
            selected_device=str(data.get("sound_device_name", data.get("audio_device_name", "")))
        )

        self.payload_frame_seconds_spin.setValue(float(data.get("sound_payload_frame_seconds", 1.0)))
        self._set_combo_data(
            self.payload_overlap_combo,
            int(float(data.get("sound_payload_overlap_percent", 50))),
            fallback_index=4,
        )
        self._set_combo_data(
            self.payload_style_combo,
            str(data.get("sound_payload_style_mode", "stack3")),
        )
        self._set_combo_data(
            self.payload_y_repeat_combo,
            int(data.get("sound_payload_y_repeat", 4)),
            fallback_index=2,
        )
        self._set_combo_data(
            self.payload_variant_combo,
            str(data.get("sound_payload_variant_mode", "none")),
        )
        self._set_combo_data(
            self.payload_preview_resize_combo,
            str(data.get("sound_payload_preview_resize_mode", "pixel")),
        )
        self.payload_overlay_grid_check.setChecked(bool(data.get("sound_payload_overlay_grid", True)))
        self.payload_overlay_time_check.setChecked(bool(data.get("sound_payload_overlay_time_ticks", True)))
        self.payload_overlay_stack_check.setChecked(bool(data.get("sound_payload_overlay_stack_bounds", True)))
        self.payload_overlay_legend_check.setChecked(bool(data.get("sound_payload_overlay_legend", True)))

        liss_tau = data.get("sound_liss_tau", 5)
        if str(liss_tau).lower() == "both":
            tau_value: object = "both"
        else:
            try:
                tau_value = int(liss_tau)
            except Exception:
                tau_value = 5
        self._set_combo_data(self.liss_tau_combo, tau_value, fallback_index=1)
        self.liss_width_spin.setValue(int(data.get("sound_liss_width", 512)))
        self.liss_height_spin.setValue(int(data.get("sound_liss_height", 512)))
        self._set_combo_data(self.liss_accum_combo, str(data.get("sound_liss_accum", "none")))
        self.liss_point_size_spin.setValue(int(data.get("sound_liss_point_size_step", 1)))
        self._set_combo_data(
            self.liss_point_style_combo,
            str(data.get("sound_liss_point_render_style", "classic")),
        )
        self._set_combo_data(
            self.liss_value_mode_combo,
            str(data.get("sound_liss_value_mode", "radial")),
        )
        self._set_combo_data(
            self.liss_rotation_combo,
            str(data.get("sound_liss_rotation", "none")),
        )

        self._set_combo_data(self.classic_preset_combo, str(data.get("sound_classic_preset", "none")))
        self._set_combo_data(self.classic_style_combo, str(data.get("sound_classic_style", "classic")))
        self._set_combo_data(self.classic_axis_combo, str(data.get("sound_classic_axis_mode", "linear")))
        self.classic_width_spin.setValue(int(data.get("sound_classic_width", 1024)))
        self.classic_height_spin.setValue(int(data.get("sound_classic_height", 768)))
        self.classic_n_fft_spin.setValue(int(data.get("sound_classic_n_fft", 4096)))
        self.classic_win_ms_spin.setValue(float(data.get("sound_classic_win_ms", 25.0)))
        self.classic_hop_ms_spin.setValue(float(data.get("sound_classic_hop_ms", 1.0)))
        self.classic_top_db_spin.setValue(float(data.get("sound_classic_top_db", 80.0)))
        self.classic_fmax_spin.setValue(float(data.get("sound_classic_fmax", 24000.0)))
        self._set_combo_data(
            self.classic_colormap_combo,
            str(data.get("sound_classic_colormap", "gray")),
        )
        self.classic_gamma_spin.setValue(float(data.get("sound_classic_gamma", 1.0)))
        self._set_combo_data(
            self.classic_detail_mode_combo,
            str(data.get("sound_classic_detail_mode", "off")),
        )
        self.classic_detail_sigma_spin.setValue(float(data.get("sound_classic_detail_sigma", 1.2)))
        self.classic_detail_gain_spin.setValue(float(data.get("sound_classic_detail_gain", 70.0)))
        self.classic_detail_p_spin.setValue(float(data.get("sound_classic_detail_p", 99.5)))
        self._set_combo_data(
            self.classic_freq_interp_combo,
            str(data.get("sound_classic_freq_interp", "auto")),
        )
        self._set_combo_data(
            self.classic_fuse7_profile_combo,
            str(data.get("sound_classic_fuse7_profile", "ref_compat")),
        )
        self._set_combo_data(
            self.classic_scale_mode_combo,
            str(data.get("sound_classic_scale_mode", "top_db")),
        )
        self.classic_p_lo_spin.setValue(float(data.get("sound_classic_p_lo", 1.0)))
        self.classic_p_hi_spin.setValue(float(data.get("sound_classic_p_hi", 99.0)))
        self.classic_n_mels_hue_spin.setValue(int(data.get("sound_classic_n_mels_hue", 128)))
        self.classic_n_mels_layers_spin.setValue(int(data.get("sound_classic_n_mels_layers", 64)))
        self.classic_norm_p_spin.setValue(float(data.get("sound_classic_norm_p", 99.5)))
        self.classic_flux_gain_spin.setValue(float(data.get("sound_classic_flux_gain", 110.0)))
        self.classic_edge_gain_spin.setValue(float(data.get("sound_classic_edge_gain", 70.0)))
        self.classic_freq_green_bias_spin.setValue(float(data.get("sound_classic_freq_green_bias", 0.15)))
        self.classic_edge_base_alpha_spin.setValue(float(data.get("sound_classic_edge_base_alpha", 0.25)))

        self.pm_tcp_enabled_check.setChecked(bool(data.get("pm_tcp_enabled", False)))
        self.pm_tcp_host_edit.setText(data.get("pm_tcp_host", "127.0.0.1"))
        self.pm_tcp_port_spin.setValue(int(data.get("pm_tcp_port", 7002)))
        policy = data.get("pm_policy", "off")
        for idx in range(self.pm_policy_combo.count()):
            if self.pm_policy_combo.itemData(idx) == policy:
                self.pm_policy_combo.setCurrentIndex(idx)
                break

        files = data.get("files") or []
        if files:
            self.selected_files = files
            self.files_label.setText(f"{len(files)} souborů")

        self.api_key_value = data.get("api_key", "")
        self.api_key_location_value = data.get("api_key_location", "query")
        self.api_key_name_value = data.get("api_key_name", "api_key")
        self._update_pm_controls()
        self._update_audio_stack()
        self._on_audio_source_changed()
        self._update_sound_send_mode_ui()
        self._update_file_actions_loop_state()
        self._update_file_actions_mode_ui()
        self._update_classic_style_ui()

    def _save_gui_settings(self) -> None:
        payload = {
            "host": self.host_edit.text().strip() or "127.0.0.1",
            "port": int(self.port_spin.value()),
            "mode": self.mode_combo.currentText(),
            "project_path": self.project_path_edit.text().strip(),
            "folder": self.folder_edit.text().strip(),
            "include_subfolders": self.include_subfolders_check.isChecked(),
            "run_mode": str(self.run_mode_combo.currentData() or "initial_then_watch"),
            "delay_ms": int(self.delay_spin.value()),
            "file_actions_enabled": self.file_actions_enable_check.isChecked(),
            "file_actions_save_json": self.file_actions_save_json_check.isChecked(),
            "file_actions_save_processed": self.file_actions_save_processed_check.isChecked(),
            "file_actions_mode": str(self.file_actions_mode_combo.currentData() or "move_by_result"),
            "file_ok_dir": self.file_ok_dir_edit.text().strip(),
            "file_ok_daily": self.file_ok_daily_check.isChecked(),
            "file_ok_hourly": self.file_ok_hourly_check.isChecked(),
            "file_ok_result_prefix": self.file_ok_result_check.isChecked(),
            "file_ok_timestamp": self.file_ok_timestamp_check.isChecked(),
            "file_ok_include_string": self.file_ok_string_check.isChecked(),
            "file_ok_string_value": self.file_ok_string_edit.text(),
            "file_nok_dir": self.file_nok_dir_edit.text().strip(),
            "file_nok_daily": self.file_nok_daily_check.isChecked(),
            "file_nok_hourly": self.file_nok_hourly_check.isChecked(),
            "file_nok_result_prefix": self.file_nok_result_check.isChecked(),
            "file_nok_timestamp": self.file_nok_timestamp_check.isChecked(),
            "file_nok_include_string": self.file_nok_string_check.isChecked(),
            "file_nok_string_value": self.file_nok_string_edit.text(),
            "data_include_filename": self.data_filename_check.isChecked(),
            "data_include_timestamp": self.data_timestamp_check.isChecked(),
            "data_include_string": self.data_string_check.isChecked(),
            "data_string_value": self.data_string_edit.text(),
            "sound_enabled": self.audio_enable_check.isChecked(),
            "sound_approach": str(self.audio_approach_combo.currentData() or "payload"),
            "sound_source": str(self.audio_source_combo.currentData() or "loopback"),
            "sound_device_name": str(self.audio_device_combo.currentData() or ""),
            "sound_backend_policy": str(self.audio_backend_policy_combo.currentData() or "auto"),
            "sound_send_mode": str(self.audio_send_mode_combo.currentData() or "save_send"),
            "sound_sample_rate_hz": int(self.audio_sample_rate_spin.value()),
            "sound_window_sec": float(self.audio_window_spin.value()),
            "sound_fps": float(self.audio_fps_spin.value()),
            "sound_interval_sec": 1.0 / max(float(self.audio_fps_spin.value()), 1e-6),
            "sound_sine_freq_hz": float(self.audio_sine_freq_spin.value()),
            "sound_snapshot_dir": self.audio_snapshot_dir_edit.text().strip(),
            "sound_file_prefix": self.audio_file_prefix_edit.text().strip() or "sound",
            "sound_payload_frame_seconds": float(self.payload_frame_seconds_spin.value()),
            "sound_payload_overlap_percent": int(self.payload_overlap_combo.currentData() or 50),
            "sound_payload_style_mode": str(self.payload_style_combo.currentData() or "stack3"),
            "sound_payload_y_repeat": int(self.payload_y_repeat_combo.currentData() or 4),
            "sound_payload_variant_mode": str(self.payload_variant_combo.currentData() or "none"),
            "sound_payload_preview_resize_mode": str(
                self.payload_preview_resize_combo.currentData() or "pixel"
            ),
            "sound_payload_overlay_grid": self.payload_overlay_grid_check.isChecked(),
            "sound_payload_overlay_time_ticks": self.payload_overlay_time_check.isChecked(),
            "sound_payload_overlay_stack_bounds": self.payload_overlay_stack_check.isChecked(),
            "sound_payload_overlay_legend": self.payload_overlay_legend_check.isChecked(),
            "sound_liss_tau": self.liss_tau_combo.currentData() or 5,
            "sound_liss_width": int(self.liss_width_spin.value()),
            "sound_liss_height": int(self.liss_height_spin.value()),
            "sound_liss_accum": str(self.liss_accum_combo.currentData() or "none"),
            "sound_liss_point_size_step": int(self.liss_point_size_spin.value()),
            "sound_liss_point_render_style": str(self.liss_point_style_combo.currentData() or "classic"),
            "sound_liss_value_mode": str(self.liss_value_mode_combo.currentData() or "radial"),
            "sound_liss_rotation": str(self.liss_rotation_combo.currentData() or "none"),
            "sound_classic_preset": str(self.classic_preset_combo.currentData() or "none"),
            "sound_classic_style": str(self.classic_style_combo.currentData() or "classic"),
            "sound_classic_axis_mode": str(self.classic_axis_combo.currentData() or "linear"),
            "sound_classic_width": int(self.classic_width_spin.value()),
            "sound_classic_height": int(self.classic_height_spin.value()),
            "sound_classic_n_fft": int(self.classic_n_fft_spin.value()),
            "sound_classic_win_ms": float(self.classic_win_ms_spin.value()),
            "sound_classic_hop_ms": float(self.classic_hop_ms_spin.value()),
            "sound_classic_top_db": float(self.classic_top_db_spin.value()),
            "sound_classic_fmax": float(self.classic_fmax_spin.value()),
            "sound_classic_colormap": str(self.classic_colormap_combo.currentData() or "gray"),
            "sound_classic_gamma": float(self.classic_gamma_spin.value()),
            "sound_classic_detail_mode": str(self.classic_detail_mode_combo.currentData() or "off"),
            "sound_classic_detail_sigma": float(self.classic_detail_sigma_spin.value()),
            "sound_classic_detail_gain": float(self.classic_detail_gain_spin.value()),
            "sound_classic_detail_p": float(self.classic_detail_p_spin.value()),
            "sound_classic_freq_interp": str(self.classic_freq_interp_combo.currentData() or "auto"),
            "sound_classic_fuse7_profile": str(self.classic_fuse7_profile_combo.currentData() or "ref_compat"),
            "sound_classic_scale_mode": str(self.classic_scale_mode_combo.currentData() or "top_db"),
            "sound_classic_p_lo": float(self.classic_p_lo_spin.value()),
            "sound_classic_p_hi": float(self.classic_p_hi_spin.value()),
            "sound_classic_n_mels_hue": int(self.classic_n_mels_hue_spin.value()),
            "sound_classic_n_mels_layers": int(self.classic_n_mels_layers_spin.value()),
            "sound_classic_norm_p": float(self.classic_norm_p_spin.value()),
            "sound_classic_flux_gain": float(self.classic_flux_gain_spin.value()),
            "sound_classic_edge_gain": float(self.classic_edge_gain_spin.value()),
            "sound_classic_freq_green_bias": float(self.classic_freq_green_bias_spin.value()),
            "sound_classic_edge_base_alpha": float(self.classic_edge_base_alpha_spin.value()),
            "pm_tcp_enabled": self.pm_tcp_enabled_check.isChecked(),
            "pm_tcp_host": self.pm_tcp_host_edit.text().strip(),
            "pm_tcp_port": int(self.pm_tcp_port_spin.value()),
            "pm_policy": self.pm_policy_combo.currentData(),
            "files": self.selected_files,
            "api_key": self.api_key_value,
            "api_key_location": self.api_key_location_value,
            "api_key_name": self.api_key_name_value,
        }
        path = self._gui_config_path()
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _setup_api_key(self) -> None:
        dialog = ApiKeyDialog(
            api_key=self.api_key_value,
            location=self.api_key_location_value,
            name=self.api_key_name_value,
            parent=self,
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.api_key_value = dialog.api_key_edit.text().strip()
            self.api_key_location_value = dialog.location_combo.currentText()
            self.api_key_name_value = dialog.name_edit.text().strip() or "api_key"

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[name-defined]
        try:
            self._save_gui_settings()
        except Exception:
            pass
        try:
            self._stop_sound_preview()
        except Exception:
            pass
        try:
            self.sound_preview_reconfig_timer.stop()
        except Exception:
            pass
        runner = self.state.runner
        if runner is not None:
            try:
                runner.set_preview_callback(None)
            except Exception:
                pass
        try:
            if self.classic_advanced_dialog is not None:
                self.classic_advanced_dialog.close()
        except Exception:
            pass
        super().closeEvent(event)


class ApiKeyDialog(QtWidgets.QDialog):
    def __init__(self, api_key: str, location: str, name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("API key setup")
        layout = QtWidgets.QFormLayout(self)

        self.api_key_edit = QtWidgets.QLineEdit(api_key)
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.location_combo = QtWidgets.QComboBox()
        self.location_combo.addItems(["query", "header"])
        self.location_combo.setCurrentText(location)
        self.name_edit = QtWidgets.QLineEdit(name)

        layout.addRow("API key", self.api_key_edit)
        layout.addRow("Location", self.location_combo)
        layout.addRow("Name", self.name_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
