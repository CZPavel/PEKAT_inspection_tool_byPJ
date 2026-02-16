import json
from pathlib import Path

from pektool.core.library_installer import LibraryInstaller


def _prepare_installer_fixture(tmp_path: Path) -> tuple[LibraryInstaller, Path]:
    resources_root = tmp_path / "resources" / "pekat_libs"
    payload_root = resources_root / "pyzbar" / "payload"
    payload_root.mkdir(parents=True, exist_ok=True)
    (payload_root / "pyzbar").mkdir(parents=True, exist_ok=True)
    (payload_root / "pyzbar" / "__init__.py").write_text("x=1", encoding="utf-8")
    manifest = {
        "library": "pyzbar",
        "payload_root": "payload",
        "target_subdir": "server",
        "items": [{"src": "pyzbar", "dst": "pyzbar"}],
    }
    manifest_path = resources_root / "pyzbar" / "install_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    installer = LibraryInstaller(resources_root=resources_root, logs_root=tmp_path / "logs")
    target_root = tmp_path / "PEKAT VISION 3.19.3"
    (target_root / "server").mkdir(parents=True, exist_ok=True)
    return installer, target_root


def test_library_manifest_load_and_plan_build(tmp_path):
    installer, target_root = _prepare_installer_fixture(tmp_path)
    plan = installer.build_plan("pyzbar", target_root)
    assert plan.target.is_valid is True
    assert len(plan.items) == 1
    assert plan.new_files == 1


def test_library_plan_validates_pekat_server_path(tmp_path):
    installer, _target_root = _prepare_installer_fixture(tmp_path)
    invalid = tmp_path / "InvalidRoot"
    plan = installer.build_plan("pyzbar", invalid)
    assert plan.target.is_valid is False
    assert "server" in (plan.target.warning or "").lower()


def test_library_plan_detects_overwrites(tmp_path):
    installer, target_root = _prepare_installer_fixture(tmp_path)
    (target_root / "server" / "pyzbar").mkdir(parents=True, exist_ok=True)
    (target_root / "server" / "pyzbar" / "__init__.py").write_text("old", encoding="utf-8")
    plan = installer.build_plan("pyzbar", target_root)
    assert plan.overwrite_files == 1
    assert plan.items[0].will_overwrite is True


def test_library_copy_with_backup(tmp_path):
    installer, target_root = _prepare_installer_fixture(tmp_path)
    (target_root / "server" / "pyzbar").mkdir(parents=True, exist_ok=True)
    (target_root / "server" / "pyzbar" / "__init__.py").write_text("old", encoding="utf-8")
    plan = installer.build_plan("pyzbar", target_root)
    result = installer.execute_plan(plan, create_backup=True)
    assert result.success is True
    assert result.backup_path is not None
    backup_root = Path(result.backup_path)
    assert backup_root.exists()


def test_library_copy_permission_error_reports_cleanly(tmp_path, monkeypatch):
    installer, target_root = _prepare_installer_fixture(tmp_path)
    plan = installer.build_plan("pyzbar", target_root)

    def _raise(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("shutil.copytree", _raise)
    result = installer.execute_plan(plan, create_backup=False)
    assert result.success is False
    assert any("denied" in err.lower() for err in result.errors)
