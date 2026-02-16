from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from ..types import ScriptAsset, ScriptCatalogIndex


SUPPORTED_EXTENSIONS = {".txt", ".py", ".pmodule"}
SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_").lower()
    return slug or "script"


def _read_text_with_fallback(path: Path) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            pass
    for encoding in ("cp1250", "latin1"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            pass
    return path.read_text(encoding="utf-8", errors="replace"), "utf-8-replace"


def _extract_description(text: str, fallback_name: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "Empty script file."

    # Prefer first non-empty comment/docstring-like line.
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("'''", '"""')):
            line = line.strip("'\" ")
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        if line:
            return line[:160]
    return f"Script: {fallback_name}"


def _guess_category(filename: str) -> str:
    lowered = filename.lower()
    mapping = [
        ("trigger", "trigger"),
        ("save", "save"),
        ("result", "result"),
        ("filter", "filter"),
        ("flow", "flow"),
        ("stop", "flow-control"),
        ("barcode", "barcode"),
        ("pyzbar", "barcode"),
        ("sobel", "image-filter"),
        ("laplac", "image-filter"),
        ("hdr", "image-filter"),
        ("logo", "rendering"),
        ("date", "rendering"),
        ("time", "rendering"),
        ("majak", "io-control"),
        ("button", "io-control"),
    ]
    for token, category in mapping:
        if token in lowered:
            return category
    return "general"


class TuningCatalog:
    def __init__(self, root: Optional[Path] = None) -> None:
        project_root = resolve_project_root()
        self.root = root or (project_root / "resources" / "code_modules")
        self.scripts_raw_dir = self.root / "scripts_raw"
        self.scripts_utf8_dir = self.root / "scripts_utf8"
        self.pmodule_dir = self.root / "pmodule"
        self.catalog_path = self.root / "catalog.json"
        self.categories_path = self.root / "categories.json"
        self.ensure_structure()

    def ensure_structure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.scripts_raw_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_utf8_dir.mkdir(parents=True, exist_ok=True)
        self.pmodule_dir.mkdir(parents=True, exist_ok=True)
        if not self.categories_path.exists():
            self.categories_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "categories": [
                            "general",
                            "trigger",
                            "flow-control",
                            "filter",
                            "image-filter",
                            "result",
                            "save",
                            "barcode",
                            "rendering",
                            "io-control",
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        if not self.catalog_path.exists():
            self.save_catalog(ScriptCatalogIndex(schema_version=SCHEMA_VERSION, generated_at=_utc_now(), items=[]))

    def load_catalog(self) -> ScriptCatalogIndex:
        self.ensure_structure()
        payload = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        items = [ScriptAsset(**item) for item in payload.get("items", [])]
        return ScriptCatalogIndex(
            schema_version=str(payload.get("schema_version", SCHEMA_VERSION)),
            generated_at=str(payload.get("generated_at", _utc_now())),
            items=items,
        )

    def save_catalog(self, catalog: ScriptCatalogIndex) -> None:
        payload = {
            "schema_version": catalog.schema_version,
            "generated_at": catalog.generated_at,
            "items": [asset.__dict__ for asset in catalog.items],
        }
        self.catalog_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _build_asset_from_file(self, source_file: Path) -> ScriptAsset:
        ext = source_file.suffix.lower()
        format_name = "pmodule" if ext == ".pmodule" else ("py" if ext == ".py" else "txt")
        source_bytes = source_file.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        slug = _slugify(source_file.stem)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        raw_name = f"{slug}_{timestamp}{ext}"
        raw_target = self.scripts_raw_dir / raw_name
        shutil.copy2(source_file, raw_target)

        text_preview = ""
        encoding_source = "binary"
        utf8_target = ""
        is_empty = len(source_bytes) == 0
        if format_name != "pmodule":
            text_preview, encoding_source = _read_text_with_fallback(source_file)
            utf8_name = f"{slug}_{timestamp}.txt"
            utf8_target_path = self.scripts_utf8_dir / utf8_name
            utf8_target_path.write_text(text_preview, encoding="utf-8")
            utf8_target = (Path("scripts_utf8") / utf8_name).as_posix()
        else:
            pmodule_target = self.pmodule_dir / f"{slug}_{timestamp}.pmodule"
            shutil.copy2(source_file, pmodule_target)
            utf8_target = ""

        description = _extract_description(text_preview, source_file.name)
        category = _guess_category(source_file.name)
        tags = [category, format_name]
        now = _utc_now()
        return ScriptAsset(
            id=f"{slug}_{timestamp}",
            name=source_file.stem,
            source_filename=source_file.name,
            storage_path_utf8=utf8_target,
            storage_path_raw=(Path("scripts_raw") / raw_name).as_posix(),
            format=format_name,  # type: ignore[arg-type]
            category=category,
            tags=tags,
            short_description=description,
            encoding_source=encoding_source,
            size_bytes=len(source_bytes),
            sha256=source_hash,
            created_at=now,
            updated_at=now,
            empty=is_empty,
        )

    def import_from_folder(self, source_dir: Path) -> ScriptCatalogIndex:
        self.ensure_structure()
        source_dir = Path(source_dir)
        if not source_dir.exists():
            raise FileNotFoundError(f"Source folder not found: {source_dir}")

        existing = self.load_catalog()
        assets = list(existing.items)
        for file_path in sorted(source_dir.iterdir(), key=lambda item: item.name.lower()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            assets.append(self._build_asset_from_file(file_path))

        catalog = ScriptCatalogIndex(schema_version=SCHEMA_VERSION, generated_at=_utc_now(), items=assets)
        self.save_catalog(catalog)
        return catalog

    def list_assets(self, search: str = "", category: str = "all") -> List[ScriptAsset]:
        catalog = self.load_catalog()
        search_term = search.strip().lower()
        selected = []
        for asset in catalog.items:
            if category and category.lower() != "all" and asset.category.lower() != category.lower():
                continue
            blob = " ".join([asset.name, asset.source_filename, asset.short_description, " ".join(asset.tags)]).lower()
            if search_term and search_term not in blob:
                continue
            selected.append(asset)
        return selected

    def get_asset_text(self, asset_id: str) -> str:
        catalog = self.load_catalog()
        for asset in catalog.items:
            if asset.id != asset_id:
                continue
            if asset.storage_path_utf8:
                path = Path(asset.storage_path_utf8)
                if not path.is_absolute():
                    path = self.root / path
                if path.exists():
                    return path.read_text(encoding="utf-8")
            if asset.storage_path_raw:
                path = Path(asset.storage_path_raw)
                if not path.is_absolute():
                    path = self.root / path
                if path.exists():
                    text, _encoding = _read_text_with_fallback(path)
                    return text
            return ""
        return ""

    def export_asset(self, asset_id: str, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        catalog = self.load_catalog()
        for asset in catalog.items:
            if asset.id != asset_id:
                continue
            source = Path(asset.storage_path_utf8 or asset.storage_path_raw)
            if not source.is_absolute():
                source = self.root / source
            if not source.exists():
                raise FileNotFoundError(f"Stored asset file missing: {source}")
            shutil.copy2(source, destination)
            return destination
        raise KeyError(f"Asset not found: {asset_id}")

    def available_categories(self) -> List[str]:
        payload = json.loads(self.categories_path.read_text(encoding="utf-8"))
        categories = payload.get("categories") or []
        seen = {str(item) for item in categories}
        for asset in self.load_catalog().items:
            seen.add(asset.category)
        return sorted(seen)
