from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import List

import yaml
from PySide6 import QtCore, QtWidgets

from ..config import AppConfig
from ..core.connection import ConnectionManager
from ..core.runner import Runner
from ..logging_setup import setup_logging
from .state import GuiState
from .widgets import LogEmitter, QtLogHandler


class MainWindow(QtWidgets.QMainWindow):
    """Main GUI window for configuration, control and live feedback."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PEKAT Inspection Tool")
        self.resize(980, 640)

        self.state = GuiState()
        self.selected_files: List[str] = []
        self.stop_requested = False
        self.stop_start_time: float | None = None
        self.last_ping_time = 0.0
        self.health_check_inflight = False

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = QtWidgets.QWidget()
        self.file_actions_tab = QtWidgets.QWidget()
        self.log_tab = QtWidgets.QWidget()
        self.json_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.config_tab, "Konfigurace")
        self.tabs.addTab(self.file_actions_tab, "Manipulace se soubory")
        self.tabs.addTab(self.log_tab, "Log")
        self.tabs.addTab(self.json_tab, "JSON")

        self._build_config_tab()
        self._build_file_actions_tab()
        self._build_log_tab()
        self._build_json_tab()

        self.emitter = LogEmitter()
        self.emitter.message.connect(self._append_log)
        self.qt_handler = QtLogHandler(self.emitter)
        self.qt_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_status)

        self._load_gui_settings()

    def _build_config_tab(self) -> None:
        layout = QtWidgets.QFormLayout(self.config_tab)

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
        folder_layout.addWidget(self.folder_edit)
        folder_layout.addWidget(browse_btn)

        self.include_subfolders_check = QtWidgets.QCheckBox("Zahrnout podsložky")
        self.include_subfolders_check.setChecked(True)

        self.file_select_btn = QtWidgets.QPushButton("Vybrat soubory")
        self.file_select_btn.clicked.connect(self._select_files)
        self.files_label = QtWidgets.QLabel("0 souborů")

        files_layout = QtWidgets.QHBoxLayout()
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
            btn.setMinimumHeight(44)
            btn.setMinimumWidth(140)

        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        btn_layout = QtWidgets.QHBoxLayout()
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
        self.nok_count_value.setMinimumHeight(70)
        self.ok_count_value.setMinimumHeight(70)
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
        count_layout.addWidget(self.count_label)
        count_layout.addWidget(self.reset_counter_btn)
        layout.addRow("Odesláno", count_layout)
        layout.addRow("Posledni vyhodnoceni (ms)", self.last_eval_time_label)
        layout.addRow("Prumerny cas (ms)", self.avg_eval_time_label)

        ok_nok_layout = QtWidgets.QHBoxLayout()
        nok_box = QtWidgets.QGroupBox("NOK")
        ok_box = QtWidgets.QGroupBox("OK")
        nok_box_layout = QtWidgets.QVBoxLayout(nok_box)
        ok_box_layout = QtWidgets.QVBoxLayout(ok_box)
        nok_box_layout.addWidget(self.nok_count_value)
        ok_box_layout.addWidget(self.ok_count_value)
        ok_nok_layout.addWidget(nok_box)
        ok_nok_layout.addWidget(ok_box)
        layout.addRow("Vyhodnoceni", ok_nok_layout)

        self.pm_tcp_enabled_check.toggled.connect(self._update_pm_controls)
        self.project_path_edit.textChanged.connect(self._update_pm_controls)
        self._update_pm_controls()
        self._update_file_actions_loop_state()

    def _build_file_actions_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.file_actions_tab)

        self.file_actions_enable_check = QtWidgets.QCheckBox("Povolit manipulaci se soubory")
        self.file_actions_info_label = QtWidgets.QLabel("")
        self.file_actions_info_label.setStyleSheet("color: #777;")

        self.file_actions_mode_combo = QtWidgets.QComboBox()
        self.file_actions_mode_combo.addItem("Po vyhodnoceni mazat soubory", "delete_after_eval")
        self.file_actions_mode_combo.addItem("Presouvat podle vyhodnoceni", "move_by_result")
        self.file_actions_mode_combo.addItem("Presun kdyz OK - Smaz kdyz NOK", "move_ok_delete_nok")
        self.file_actions_mode_combo.addItem("Smaz kdyz OK - Presun kdyz NOK", "delete_ok_move_nok")

        top_form = QtWidgets.QFormLayout()
        top_form.addRow("", self.file_actions_enable_check)
        top_form.addRow("Rezim manipulace", self.file_actions_mode_combo)
        top_form.addRow("", self.file_actions_info_label)
        layout.addLayout(top_form)

        self.file_ok_group = QtWidgets.QGroupBox("Sekce OK")
        ok_layout = QtWidgets.QFormLayout(self.file_ok_group)
        self.file_ok_dir_edit = QtWidgets.QLineEdit("")
        self.file_ok_browse_btn = QtWidgets.QToolButton()
        self.file_ok_browse_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.file_ok_browse_btn.setToolTip("Vybrat cilovou slozku")
        self.file_ok_browse_btn.clicked.connect(lambda: self._select_target_dir(self.file_ok_dir_edit))
        ok_dir_layout = QtWidgets.QHBoxLayout()
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
        self.file_nok_dir_edit = QtWidgets.QLineEdit("")
        self.file_nok_browse_btn = QtWidgets.QToolButton()
        self.file_nok_browse_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        self.file_nok_browse_btn.setToolTip("Vybrat cilovou slozku")
        self.file_nok_browse_btn.clicked.connect(lambda: self._select_target_dir(self.file_nok_dir_edit))
        nok_dir_layout = QtWidgets.QHBoxLayout()
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
        sections_layout.addWidget(self.file_ok_group)
        sections_layout.addWidget(self.file_nok_group)
        layout.addLayout(sections_layout)
        layout.addStretch(1)

        self.file_actions_enable_check.toggled.connect(self._update_file_actions_mode_ui)
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
        if is_loop_mode:
            self.file_actions_enable_check.blockSignals(True)
            self.file_actions_enable_check.setChecked(False)
            self.file_actions_enable_check.blockSignals(False)
            self.file_actions_enable_check.setEnabled(False)
            self.file_actions_info_label.setText("V rezimu Loop neni funkcionalita dostupna.")
        else:
            self.file_actions_enable_check.setEnabled(True)
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

        enabled = self.file_actions_enable_check.isChecked() and self.file_actions_enable_check.isEnabled()
        mode = str(self.file_actions_mode_combo.currentData() or "move_by_result")
        self.file_actions_mode_combo.setEnabled(enabled)

        ok_needs_target = mode in {"move_by_result", "move_ok_delete_nok"}
        nok_needs_target = mode in {"move_by_result", "delete_ok_move_nok"}
        self.file_ok_group.setEnabled(enabled and ok_needs_target)
        self.file_nok_group.setEnabled(enabled and nok_needs_target)
        self._update_file_actions_string_edits()

    def _build_log_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.log_tab)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def _build_json_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.json_tab)
        self.json_view = QtWidgets.QTextEdit()
        self.json_view.setReadOnly(True)
        self.json_view.setPlainText("{}")
        layout.addWidget(self.json_view)

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
        cfg.file_actions.enabled = bool(
            self.file_actions_enable_check.isChecked()
            and str(self.run_mode_combo.currentData() or "") != "loop"
        )
        cfg.file_actions.mode = str(self.file_actions_mode_combo.currentData() or "move_by_result")
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
        cfg = self._gather_config()
        self.state.config = cfg
        logger = self.state.connection.logger if self.state.connection else setup_logging(cfg.logging)
        logger.addHandler(self.qt_handler)
        runner = Runner(cfg, self.state.connection, logger)
        runner.start()

        self.stop_requested = False
        self.stop_start_time = None
        self.state.runner = runner
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.timer.start()

    def _stop(self) -> None:
        if not self.state.runner:
            return
        self.stop_requested = True
        self.stop_start_time = time.time()
        self.stop_btn.setEnabled(False)
        self.send_status_label.setText("stopping")

        def _stop_worker() -> None:
            if self.state.runner:
                self.state.runner.stop()

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

        config_enabled = not (connected or connecting or sending)
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
            self.file_actions_mode_combo,
            self.file_ok_group,
            self.file_nok_group,
            self.data_filename_check,
            self.data_timestamp_check,
            self.data_string_check,
            self.data_string_edit,
        ]

        for widget in connection_widgets:
            widget.setEnabled(not (connected or connecting))
        for widget in sending_widgets:
            widget.setEnabled(not sending)

        if not (connected or connecting):
            self._update_pm_controls()
            self._update_file_actions_loop_state()
        self.data_string_edit.setEnabled(self.data_string_check.isChecked() and not sending)
        self._update_file_actions_string_edits()

    def _gui_config_path(self) -> Path:
        return Path.home() / ".pektool_gui.yaml"

    def _set_run_mode_combo(self, run_mode: str) -> None:
        for idx in range(self.run_mode_combo.count()):
            if self.run_mode_combo.itemData(idx) == run_mode:
                self.run_mode_combo.setCurrentIndex(idx)
                return
        self.run_mode_combo.setCurrentIndex(2)

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
        self.mode_combo.setCurrentText("rest")
        self.project_path_edit.setText(data.get("project_path", ""))
        self.folder_edit.setText(data.get("folder", ""))
        self.include_subfolders_check.setChecked(bool(data.get("include_subfolders", True)))
        self._set_run_mode_combo(str(data.get("run_mode", "initial_then_watch")))
        self.delay_spin.setValue(int(data.get("delay_ms", 150)))
        self.file_actions_enable_check.setChecked(bool(data.get("file_actions_enabled", False)))
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
        self._update_file_actions_loop_state()
        self._update_file_actions_mode_ui()

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
