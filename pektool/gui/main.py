from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import List

import yaml
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
        self.stop_requested = False
        self.stop_start_time: float | None = None

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        self.config_tab = QtWidgets.QWidget()
        self.log_tab = QtWidgets.QWidget()

        self.tabs.addTab(self.config_tab, "Konfigurace")
        self.tabs.addTab(self.log_tab, "Log")

        self._build_config_tab()
        self._build_log_tab()

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
        self.run_mode_combo.setCurrentText("initial_then_watch")

        self.delay_spin = QtWidgets.QSpinBox()
        self.delay_spin.setRange(0, 600000)
        self.delay_spin.setValue(150)

        self.data_prefix_edit = QtWidgets.QLineEdit("")

        self.api_key_value = ""
        self.api_key_location_value = "query"
        self.api_key_name_value = "api_key"
        self.api_key_button = QtWidgets.QPushButton("API key setup")
        self.api_key_button.clicked.connect(self._setup_api_key)

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
        layout.addRow("API key", self.api_key_button)

        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(44)
        self.stop_btn.setMinimumHeight(44)
        self.start_btn.setMinimumWidth(150)
        self.stop_btn.setMinimumWidth(150)

        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)

        self.status_label = QtWidgets.QLabel("stopped")
        self.count_label = QtWidgets.QLabel("0")

        layout.addRow(btn_layout)
        layout.addRow("Status", self.status_label)
        layout.addRow("Odesláno", self.count_label)

    def _build_log_tab(self) -> None:
        layout = QtWidgets.QVBoxLayout(self.log_tab)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

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

        cfg.rest.api_key = self.api_key_value
        cfg.rest.api_key_location = self.api_key_location_value
        cfg.rest.api_key_name = self.api_key_name_value or "api_key"

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
        self._save_gui_settings()
        logger = setup_logging(cfg.logging)
        logger.addHandler(self.qt_handler)
        client = self._create_client(cfg)
        runner = Runner(cfg, client, logger)
        runner.start()

        self.stop_requested = False
        self.stop_start_time = None
        self.state.runner = runner
        self.state.client = client
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.timer.start()

    def _stop(self) -> None:
        if not self.state.runner:
            return
        self.stop_requested = True
        self.stop_start_time = time.time()
        self.stop_btn.setEnabled(False)
        self.status_label.setText("stopping")

        def _stop_worker() -> None:
            if self.state.runner:
                self.state.runner.stop()
            if self.state.client:
                self.state.client.stop()

        threading.Thread(target=_stop_worker, daemon=True).start()

    def _update_status(self) -> None:
        runner = self.state.runner
        if not runner:
            self.status_label.setText("stopped")
            self.count_label.setText("0")
            return
        if self.stop_requested:
            elapsed = int(time.time() - (self.stop_start_time or time.time()))
            self.status_label.setText(f"stopping ({elapsed}s)")
        else:
            self.status_label.setText(runner.get_status())
        self.count_label.setText(str(runner.get_count()))
        if runner.get_status() == "stopped":
            self.timer.stop()
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.stop_requested = False

    def _append_log(self, message: str) -> None:
        self.log_view.append(message)

    def _gui_config_path(self) -> Path:
        return Path.home() / ".pektool_gui.yaml"

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
        self.mode_combo.setCurrentText(data.get("mode", "rest"))
        self.project_path_edit.setText(data.get("project_path", ""))
        self.start_mode_combo.setCurrentText(data.get("start_mode", "auto"))
        self.folder_edit.setText(data.get("folder", ""))
        self.include_subfolders_check.setChecked(bool(data.get("include_subfolders", True)))
        self.run_mode_combo.setCurrentText(data.get("run_mode", "initial_then_watch"))
        self.delay_spin.setValue(int(data.get("delay_ms", 150)))
        self.data_prefix_edit.setText(data.get("data_prefix", ""))

        files = data.get("files") or []
        if files:
            self.selected_files = files
            self.files_label.setText(f"{len(files)} souborů")

        self.api_key_value = data.get("api_key", "")
        self.api_key_location_value = data.get("api_key_location", "query")
        self.api_key_name_value = data.get("api_key_name", "api_key")

    def _save_gui_settings(self) -> None:
        payload = {
            "host": self.host_edit.text().strip() or "127.0.0.1",
            "port": int(self.port_spin.value()),
            "mode": self.mode_combo.currentText(),
            "project_path": self.project_path_edit.text().strip(),
            "start_mode": self.start_mode_combo.currentText(),
            "folder": self.folder_edit.text().strip(),
            "include_subfolders": self.include_subfolders_check.isChecked(),
            "run_mode": self.run_mode_combo.currentText(),
            "delay_ms": int(self.delay_spin.value()),
            "data_prefix": self.data_prefix_edit.text(),
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
