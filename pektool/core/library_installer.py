from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..types import InstallPlan, InstallPlanItem, InstallResult, InstallTarget
from .tuning_catalog import resolve_project_root


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _version_tuple_from_name(name: str) -> tuple[int, int, int]:
    match = re.search(r"PEKAT VISION\s+(\d+)\.(\d+)\.(\d+)", name, re.IGNORECASE)
    if not match:
        return (-1, -1, -1)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


class LibraryInstaller:
    def __init__(self, resources_root: Optional[Path] = None, logs_root: Optional[Path] = None) -> None:
        project_root = resolve_project_root()
        self.resources_root = resources_root or (project_root / "resources" / "pekat_libs")
        self.logs_root = logs_root or (project_root / "logs" / "installer")
        self.logs_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def detect_default_pekat_root() -> Path:
        base = Path(r"C:\Program Files")
        candidates = [path for path in base.glob("PEKAT VISION*") if path.is_dir()]
        candidates.sort(key=lambda item: (_version_tuple_from_name(item.name), item.name.lower()), reverse=True)
        if candidates:
            return candidates[0]
        return Path(r"C:\Program Files\PEKAT VISION 3.19.3")

    @staticmethod
    def validate_target(pekat_root: Path) -> InstallTarget:
        pekat_root = Path(pekat_root)
        server_path = pekat_root / "server"
        detected_version = pekat_root.name.replace("PEKAT VISION", "").strip()
        warning = None
        is_valid = pekat_root.exists() and server_path.exists()
        if not is_valid:
            warning = "Selected path does not contain PEKAT server folder."
        return InstallTarget(
            pekat_root=str(pekat_root),
            server_path=str(server_path),
            detected_version=detected_version,
            is_valid=is_valid,
            warning=warning,
        )

    def _manifest_path(self, library_name: str) -> Path:
        return self.resources_root / library_name / "install_manifest.json"

    def load_manifest(self, library_name: str) -> Dict[str, object]:
        manifest_path = self._manifest_path(library_name)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Install manifest not found: {manifest_path}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def validate_manifest_payload(self, library_name: str) -> List[str]:
        manifest = self.load_manifest(library_name)
        items_manifest: List[dict] = list(manifest.get("items") or [])
        payload_root = self.resources_root / library_name / str(manifest.get("payload_root", "payload"))
        missing = []
        for item in items_manifest:
            rel_src = str(item.get("src", "")).strip()
            if not rel_src:
                continue
            src = payload_root / rel_src
            if not src.exists():
                missing.append(str(src))
        return missing

    def build_plan(self, library_name: str, pekat_root: Path) -> InstallPlan:
        manifest = self.load_manifest(library_name)
        target = self.validate_target(pekat_root)
        if not target.is_valid:
            return InstallPlan(
                library_name=library_name,
                target=target,
                items=[],
                new_files=0,
                overwrite_files=0,
                total_size=0,
            )

        items_manifest: List[dict] = list(manifest.get("items") or [])
        payload_root = self.resources_root / library_name / str(manifest.get("payload_root", "payload"))
        target_subdir = str(manifest.get("target_subdir", "server"))

        plan_items: List[InstallPlanItem] = []
        total_size = 0
        new_files = 0
        overwrite_files = 0

        for item in items_manifest:
            rel_src = str(item.get("src", "")).strip()
            rel_dst = str(item.get("dst", rel_src)).strip()
            if not rel_src:
                continue
            src = payload_root / rel_src
            dst_root = Path(target.pekat_root) / target_subdir
            dst = dst_root / rel_dst
            if not src.exists():
                continue
            size = src.stat().st_size if src.is_file() else sum(
                child.stat().st_size for child in src.rglob("*") if child.is_file()
            )
            exists = dst.exists()
            if exists:
                overwrite_files += 1
            else:
                new_files += 1
            total_size += size
            plan_items.append(
                InstallPlanItem(
                    src=str(src),
                    dst=str(dst),
                    exists=exists,
                    will_overwrite=exists,
                    size=size,
                )
            )

        return InstallPlan(
            library_name=library_name,
            target=target,
            items=plan_items,
            new_files=new_files,
            overwrite_files=overwrite_files,
            total_size=total_size,
        )

    @staticmethod
    def detect_running_pekat_processes() -> List[str]:
        try:
            completed = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            if completed.returncode != 0:
                return []
            processes = []
            for line in completed.stdout.splitlines():
                if "PEKAT" in line.upper():
                    processes.append(line.split(",")[0].strip('"'))
            return sorted(set(processes))
        except Exception:
            return []

    @staticmethod
    def has_write_access(path: Path) -> bool:
        test_file = Path(path) / f".write_test_{os.getpid()}.tmp"
        try:
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def execute_plan(self, plan: InstallPlan, create_backup: bool = True) -> InstallResult:
        if not plan.target.is_valid:
            return InstallResult(
                success=False,
                copied=0,
                overwritten=0,
                backup_path=None,
                errors=[plan.target.warning or "Invalid target path."],
            )

        copied = 0
        overwritten = 0
        errors: List[str] = []
        backup_dir: Optional[Path] = None
        if create_backup:
            backup_dir = self.logs_root / "installer_backups" / f"{plan.library_name}_{_timestamp()}"
            backup_dir.mkdir(parents=True, exist_ok=True)

        for item in plan.items:
            src = Path(item.src)
            dst = Path(item.dst)
            try:
                if item.will_overwrite and create_backup and backup_dir is not None and dst.exists():
                    relative = Path(*dst.parts[1:]) if len(dst.parts) > 1 else dst
                    backup_target = backup_dir / relative
                    backup_target.parent.mkdir(parents=True, exist_ok=True)
                    if dst.is_dir():
                        if backup_target.exists():
                            shutil.rmtree(backup_target)
                        shutil.copytree(dst, backup_target)
                    else:
                        shutil.copy2(dst, backup_target)

                dst.parent.mkdir(parents=True, exist_ok=True)
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
                copied += 1
                if item.will_overwrite:
                    overwritten += 1
            except Exception as exc:
                errors.append(f"{src} -> {dst}: {exc}")

        success = len(errors) == 0
        return InstallResult(
            success=success,
            copied=copied,
            overwritten=overwritten,
            backup_path=str(backup_dir) if backup_dir else None,
            errors=errors,
        )
