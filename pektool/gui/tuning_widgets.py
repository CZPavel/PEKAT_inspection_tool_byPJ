from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.library_installer import LibraryInstaller
from ..core.tuning_catalog import TuningCatalog
from ..types import InstallPlan, ScriptAsset


DEFAULT_BASE_SCRIPTS_DIR = Path(r"C:\Users\P_J\Desktop\SCRIPTY_PEKAT_CODE")


class PyzbarInstallWizard(QtWidgets.QWizard):
    def __init__(self, installer: LibraryInstaller, parent=None) -> None:
        super().__init__(parent)
        self.installer = installer
        self.plan: Optional[InstallPlan] = None
        self.install_result = None
        self.executed = False

        self.setWindowTitle("Install pyzbar into PEKAT")
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self._build_pages()

    def _build_pages(self) -> None:
        intro_page = QtWidgets.QWizardPage()
        intro_page.setTitle("Intro + warning")
        intro_layout = QtWidgets.QVBoxLayout(intro_page)
        intro_layout.addWidget(
            QtWidgets.QLabel(
                "This wizard installs pyzbar files into PEKAT server directory.\n"
                "It can overwrite files in your PEKAT installation.\n"
                "Use backup option (recommended)."
            )
        )
        self.addPage(intro_page)

        target_page = QtWidgets.QWizardPage()
        target_page.setTitle("Select PEKAT path")
        target_layout = QtWidgets.QFormLayout(target_page)
        self.target_edit = QtWidgets.QLineEdit(str(self.installer.detect_default_pekat_root()))
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_target)
        target_row = QtWidgets.QHBoxLayout()
        target_row.addWidget(self.target_edit)
        target_row.addWidget(browse_btn)
        self.target_status_label = QtWidgets.QLabel("")
        target_layout.addRow("PEKAT root", target_row)
        target_layout.addRow("", self.target_status_label)
        self.addPage(target_page)

        precheck_page = QtWidgets.QWizardPage()
        precheck_page.setTitle("Pre-check")
        precheck_layout = QtWidgets.QVBoxLayout(precheck_page)
        self.precheck_view = QtWidgets.QTextEdit()
        self.precheck_view.setReadOnly(True)
        precheck_layout.addWidget(self.precheck_view)
        self.addPage(precheck_page)

        dryrun_page = QtWidgets.QWizardPage()
        dryrun_page.setTitle("Dry-run summary")
        dryrun_layout = QtWidgets.QVBoxLayout(dryrun_page)
        self.backup_check = QtWidgets.QCheckBox("Create backup before overwrite")
        self.backup_check.setChecked(True)
        self.dryrun_view = QtWidgets.QTextEdit()
        self.dryrun_view.setReadOnly(True)
        dryrun_layout.addWidget(self.backup_check)
        dryrun_layout.addWidget(self.dryrun_view)
        self.addPage(dryrun_page)

        execute_page = QtWidgets.QWizardPage()
        execute_page.setTitle("Execute")
        execute_layout = QtWidgets.QVBoxLayout(execute_page)
        self.execute_view = QtWidgets.QTextEdit()
        self.execute_view.setReadOnly(True)
        execute_layout.addWidget(self.execute_view)
        self.addPage(execute_page)

    def _browse_target(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "Select PEKAT root")
        if selected:
            self.target_edit.setText(selected)

    def _target_path(self) -> Path:
        return Path(self.target_edit.text().strip())

    def validateCurrentPage(self) -> bool:
        current_id = self.currentId()
        if current_id == 1:
            target = self.installer.validate_target(self._target_path())
            if not target.is_valid:
                self.target_status_label.setText(target.warning or "Invalid PEKAT path.")
                return False
            self.target_status_label.setText("Path looks valid.")
            return True
        return super().validateCurrentPage()

    def initializePage(self, page_id: int) -> None:
        super().initializePage(page_id)
        if page_id == 2:
            self._load_precheck()
        elif page_id == 3:
            self._load_dryrun()
        elif page_id == 4:
            self._execute_install()

    def _load_precheck(self) -> None:
        target = self.installer.validate_target(self._target_path())
        lines = [
            f"PEKAT root: {target.pekat_root}",
            f"Server path: {target.server_path}",
            f"Detected version: {target.detected_version or '-'}",
            f"Target valid: {target.is_valid}",
        ]
        writable = self.installer.has_write_access(Path(target.server_path)) if target.is_valid else False
        lines.append(f"Writable server path: {writable}")
        running = self.installer.detect_running_pekat_processes()
        if running:
            lines.append("Running PEKAT-related processes detected:")
            lines.extend([f"  - {item}" for item in running])
        else:
            lines.append("No PEKAT-related process detected by tasklist.")
        self.precheck_view.setPlainText("\n".join(lines))

    def _load_dryrun(self) -> None:
        self.plan = self.installer.build_plan("pyzbar", self._target_path())
        if not self.plan.target.is_valid:
            self.dryrun_view.setPlainText(self.plan.target.warning or "Invalid target path.")
            return
        payload = {
            "library": self.plan.library_name,
            "target": self.plan.target.__dict__,
            "summary": {
                "items": len(self.plan.items),
                "new_files": self.plan.new_files,
                "overwrite_files": self.plan.overwrite_files,
                "total_size": self.plan.total_size,
            },
            "items": [item.__dict__ for item in self.plan.items],
        }
        self.dryrun_view.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

    def _execute_install(self) -> None:
        if self.executed:
            return
        self.executed = True
        if not self.plan:
            self.execute_view.setPlainText("No install plan available.")
            return
        result = self.installer.execute_plan(self.plan, create_backup=self.backup_check.isChecked())
        self.install_result = result
        payload = {
            "success": result.success,
            "copied": result.copied,
            "overwritten": result.overwritten,
            "backup_path": result.backup_path,
            "errors": result.errors,
        }
        self.execute_view.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))


class PekatTuningTab(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.catalog = TuningCatalog()
        self.installer = LibraryInstaller()
        self.current_assets: List[ScriptAsset] = []
        self.current_asset_id: Optional[str] = None
        self._build_ui()
        self._refresh_catalog()

    def _build_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)

        scripts_group = QtWidgets.QGroupBox("Code Module Script Catalog")
        scripts_layout = QtWidgets.QVBoxLayout(scripts_group)
        toolbar_layout = QtWidgets.QHBoxLayout()
        self.import_btn = QtWidgets.QPushButton("Import base scripts")
        self.refresh_btn = QtWidgets.QPushButton("Refresh catalog")
        self.copy_btn = QtWidgets.QPushButton("Copy as text")
        self.export_btn = QtWidgets.QPushButton("Export selected...")
        self.open_storage_btn = QtWidgets.QPushButton("Open storage folder")
        toolbar_layout.addWidget(self.import_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.copy_btn)
        toolbar_layout.addWidget(self.export_btn)
        toolbar_layout.addWidget(self.open_storage_btn)
        toolbar_layout.addStretch(1)
        scripts_layout.addLayout(toolbar_layout)

        filter_layout = QtWidgets.QHBoxLayout()
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, tag, description...")
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.addItem("all")
        filter_layout.addWidget(QtWidgets.QLabel("Filter"))
        filter_layout.addWidget(self.search_edit, 2)
        filter_layout.addWidget(QtWidgets.QLabel("Category"))
        filter_layout.addWidget(self.category_combo, 1)
        scripts_layout.addLayout(filter_layout)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        self.script_table = QtWidgets.QTableWidget(0, 6)
        self.script_table.setHorizontalHeaderLabels(
            ["Name", "Format", "Category", "Description", "Updated", "Source"]
        )
        self.script_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.script_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.script_table.verticalHeader().setVisible(False)
        self.script_table.horizontalHeader().setStretchLastSection(True)
        left_layout.addWidget(self.script_table)

        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        self.script_meta_label = QtWidgets.QLabel("Select script to show preview.")
        self.script_preview = QtWidgets.QTextEdit()
        self.script_preview.setReadOnly(True)
        right_layout.addWidget(self.script_meta_label)
        right_layout.addWidget(self.script_preview)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([550, 550])
        scripts_layout.addWidget(splitter)

        root_layout.addWidget(scripts_group, 3)

        libs_group = QtWidgets.QGroupBox("Library Installer")
        libs_layout = QtWidgets.QVBoxLayout(libs_group)
        info_label = QtWidgets.QLabel(
            "Install extension libraries into PEKAT server path using guided wizard."
        )
        libs_layout.addWidget(info_label)
        buttons_layout = QtWidgets.QHBoxLayout()
        self.install_pyzbar_btn = QtWidgets.QPushButton("Install pyzbar")
        self.install_placeholder_2_btn = QtWidgets.QPushButton("Install library #2")
        self.install_placeholder_3_btn = QtWidgets.QPushButton("Install library #3")
        self.install_placeholder_4_btn = QtWidgets.QPushButton("Install library #4")
        self.install_placeholder_2_btn.setEnabled(False)
        self.install_placeholder_3_btn.setEnabled(False)
        self.install_placeholder_4_btn.setEnabled(False)
        buttons_layout.addWidget(self.install_pyzbar_btn)
        buttons_layout.addWidget(self.install_placeholder_2_btn)
        buttons_layout.addWidget(self.install_placeholder_3_btn)
        buttons_layout.addWidget(self.install_placeholder_4_btn)
        buttons_layout.addStretch(1)
        libs_layout.addLayout(buttons_layout)
        self.install_status_label = QtWidgets.QLabel("Ready.")
        libs_layout.addWidget(self.install_status_label)
        root_layout.addWidget(libs_group, 1)

        self.import_btn.clicked.connect(self._import_base_scripts)
        self.refresh_btn.clicked.connect(self._refresh_catalog)
        self.copy_btn.clicked.connect(self._copy_selected_text)
        self.export_btn.clicked.connect(self._export_selected)
        self.open_storage_btn.clicked.connect(self._open_storage_folder)
        self.search_edit.textChanged.connect(self._refresh_catalog)
        self.category_combo.currentIndexChanged.connect(self._refresh_catalog)
        self.script_table.itemSelectionChanged.connect(self._on_script_selection_changed)
        self.install_pyzbar_btn.clicked.connect(self._run_pyzbar_install_wizard)

    @staticmethod
    def _set_item(table: QtWidgets.QTableWidget, row: int, col: int, text: str) -> None:
        table.setItem(row, col, QtWidgets.QTableWidgetItem(text))

    def _refresh_categories(self) -> None:
        current = self.category_combo.currentText()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("all")
        for category in self.catalog.available_categories():
            self.category_combo.addItem(category)
        index = self.category_combo.findText(current)
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        self.category_combo.blockSignals(False)

    def _refresh_catalog(self) -> None:
        self._refresh_categories()
        assets = self.catalog.list_assets(
            search=self.search_edit.text(),
            category=self.category_combo.currentText(),
        )
        self.current_assets = assets
        self.script_table.setRowCount(len(assets))
        for row, asset in enumerate(assets):
            self._set_item(self.script_table, row, 0, asset.name)
            self._set_item(self.script_table, row, 1, asset.format)
            self._set_item(self.script_table, row, 2, asset.category)
            self._set_item(self.script_table, row, 3, asset.short_description)
            self._set_item(self.script_table, row, 4, asset.updated_at)
            self._set_item(self.script_table, row, 5, asset.source_filename)
        self.script_table.resizeColumnsToContents()
        if assets:
            self.script_table.selectRow(0)
        else:
            self.current_asset_id = None
            self.script_preview.setPlainText("")
            self.script_meta_label.setText("No scripts in catalog.")

    def _selected_asset(self) -> Optional[ScriptAsset]:
        selected_rows = self.script_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if 0 <= row < len(self.current_assets):
            return self.current_assets[row]
        return None

    def _on_script_selection_changed(self) -> None:
        asset = self._selected_asset()
        if not asset:
            return
        self.current_asset_id = asset.id
        text = self.catalog.get_asset_text(asset.id)
        self.script_preview.setPlainText(text)
        self.script_meta_label.setText(
            f"{asset.name} | format={asset.format} | category={asset.category} | encoding={asset.encoding_source}"
        )

    def _import_base_scripts(self) -> None:
        source = DEFAULT_BASE_SCRIPTS_DIR
        if not source.exists():
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Select script source folder",
                str(Path.home()),
            )
            if not folder:
                return
            source = Path(folder)

        self.catalog.import_from_folder(source)
        self._refresh_catalog()
        self.install_status_label.setText(f"Imported scripts from: {source}")

    def _copy_selected_text(self) -> None:
        asset = self._selected_asset()
        if not asset:
            return
        text = self.catalog.get_asset_text(asset.id)
        QtWidgets.QApplication.clipboard().setText(text)
        self.install_status_label.setText(f"Copied script text: {asset.name}")

    def _export_selected(self) -> None:
        asset = self._selected_asset()
        if not asset:
            return
        suggested = f"{asset.name}.txt"
        target, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export script",
            suggested,
            "Text files (*.txt);;All files (*.*)",
        )
        if not target:
            return
        self.catalog.export_asset(asset.id, Path(target))
        self.install_status_label.setText(f"Exported to: {target}")

    def _open_storage_folder(self) -> None:
        url = QtCore.QUrl.fromLocalFile(str(self.catalog.root))
        QtGui.QDesktopServices.openUrl(url)

    def _run_pyzbar_install_wizard(self) -> None:
        wizard = PyzbarInstallWizard(self.installer, parent=self)
        result = wizard.exec()
        if result == QtWidgets.QDialog.Accepted:
            self.install_status_label.setText("pyzbar installation wizard finished.")
        else:
            self.install_status_label.setText("pyzbar installation wizard canceled.")

