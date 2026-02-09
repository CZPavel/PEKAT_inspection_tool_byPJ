from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from PySide6 import QtCore, QtWidgets

from ..clients.rest_client import RestClient
from ..clients.sdk_client import SDKClient
from ..config import AppConfig
from ..core.runner import Runner
from ..logging_setup import setup_logging
from .state import GuiState
from .widgets import LogEmitter, QtLogHandler


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PEKAT Inspection Tool")
        self.resize(980, 640)

        self.state = GuiState()
        self.selected_files: List[str] = []

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = QtWidgets.QWidget()
        self.run_tab = QtWidgets.QWidget()
        self.log_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.config_tab, "Konfigurace")
        self.tabs.addTab(self.run_tab, "Běh")
        self.tabs.addTab(self.log_tab, "Log")

        self._build_config_tab()
        self._build_run_tab()
        self._build_log_tab()

        self.emitter = LogEmitter()
        self.emitter.message.connect(self._append_log)
        self.qt_handler = QtLogHandler(self.emitter)
        self.qt_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_status)

    def _build_config_tab(self) -> None:
        layout = QtWidgets.QFormLayout(self.config_tab)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["sdk", "rest"])

        self.host_edit = QtWidgets.QLineEdit("127.0.0.1")
        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(8000)

        self.project_path_edit = QtWidgets.QLineEdit("")

        self.start_mode_combo = QtWidgets.QComboBox()
        self.start_mode_combo.addItems(["auto", "connect_only", "always_start"])

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
        self.run_mode_combo.addItems(["loop", "once", "initial_then_watch"])

        self.delay_spin = QtWidgets.QSpinBox()
        self.delay_spin.setRange(0, 600000)
        self.delay_spin.setValue(0)

        self.data_prefix_edit = QtWidgets.QLineEdit("")

        self.api_key_edit = QtWidgets.QLineEdit("")
        self.api_key_location = QtWidgets.QComboBox()
        self.api_key_location.addItems(["query", "header"])
        self.api_key_name = QtWidgets.QLineEdit("api_key")

        layout.addRow("Režim (SDK/REST)", self.mode_combo)
        layout.addRow("Host", self.host_edit)
        layout.addRow("Port", self.port_spin)
        layout.addRow("Project path", self.project_path_edit)
        layout.addRow("Start mode", self.start_mode_combo)
        layout.addRow("Složka", folder_layout)
        layout.addRow("", self.include_subfolders_check)
        layout.addRow("Soubory", files_layout)
        layout.addRow("Režim běhu", self.run_mode_combo)
        layout.addRow("Prodleva (ms)", self.delay_spin)
        layout.addRow("Data prefix", self.data_prefix_edit)
        layout.addRow("API key", self.api_key_edit)
        layout.addRow("API key location", self.api_key_location)
        layout.addRow("API key name", self.api_key_name)

    def _build_run_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.run_tab)

        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)

        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        self.status_label = QtWidgets.QLabel("Status: stopped")
        self.count_label = QtWidgets.QLabel("Odesláno: 0")

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.count_label)
        layout.addStretch(1)

    def _build_log_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.log_tab)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

    def _select_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Vyberte složku")
        if folder:
            self.folder_edit.setText(folder)

    def _select_files(self) -> None:
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Vyberte soubory")
        if files:
            self.selected_files = files
            self.files_label.setText(f"{len(files)} souborů")

    def _gather_config(self) -> AppConfig:
        cfg = AppConfig()
        cfg.mode = self.mode_combo.currentText()
        cfg.host = self.host_edit.text().strip() or "127.0.0.1"
        cfg.port = int(self.port_spin.value())
        cfg.project_path = self.project_path_edit.text().strip()
        cfg.start_mode = self.start_mode_combo.currentText()

        cfg.input.folder = self.folder_edit.text().strip()
        cfg.input.include_subfolders = self.include_subfolders_check.isChecked()
        if self.selected_files:
            cfg.input.source_type = "files"
            cfg.input.files = self.selected_files
        else:
            cfg.input.source_type = "folder"

        cfg.behavior.run_mode = self.run_mode_combo.currentText()
        cfg.behavior.delay_between_images_ms = int(self.delay_spin.value())
        cfg.pekat.data_prefix = self.data_prefix_edit.text()

        cfg.rest.api_key = self.api_key_edit.text().strip()
        cfg.rest.api_key_location = self.api_key_location.currentText()
        cfg.rest.api_key_name = self.api_key_name.text().strip() or "api_key"

        return cfg

    def _create_client(self, cfg: AppConfig):
        if cfg.mode == "rest":
            return RestClient(
                host=cfg.host,
                port=cfg.port,
                api_key=cfg.rest.api_key,
                api_key_location=cfg.rest.api_key_location,
                api_key_name=cfg.rest.api_key_name,
                use_session=cfg.rest.use_session,
            )
        return SDKClient(
            host=cfg.host,
            port=cfg.port,
            project_path=cfg.project_path,
            start_mode=cfg.start_mode,
            already_running=cfg.already_running,
        )

    def _start(self) -> None:
        cfg = self._gather_config()
        logger = setup_logging(cfg.logging)
        logger.addHandler(self.qt_handler)
        client = self._create_client(cfg)
        runner = Runner(cfg, client, logger)
        runner.start()

        self.state.runner = runner
        self.state.client = client
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.timer.start()

    def _stop(self) -> None:
        if self.state.runner:
            self.state.runner.stop()
        if self.state.client:
            self.state.client.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.timer.stop()

    def _update_status(self) -> None:
        runner = self.state.runner
        if not runner:
            self.status_label.setText("Status: stopped")
            self.count_label.setText("Odesláno: 0")
            return
        self.status_label.setText(f"Status: {runner.get_status()}")
        self.count_label.setText(f"Odesláno: {runner.get_count()}")

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)


def main() -> None:
    app = QtWidgets.QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
