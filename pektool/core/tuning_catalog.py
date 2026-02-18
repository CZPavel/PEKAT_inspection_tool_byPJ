from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..types import ScriptAsset, ScriptCatalogIndex


SUPPORTED_EXTENSIONS = {".txt", ".py", ".pmodule"}
SCHEMA_VERSION = "1.0"
DEFAULT_CATEGORY_ORDER = [
    "Flow control",
    "Zprac. obrazu",
    "Detekce",
    "Ukladani",
    "Ukladani/overlay",
    "Mereni",
    "Geometrie",
    "IO-Link",
    "Obecne",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _normalize_category(value: str) -> str:
    token = value.strip()
    mapping = {
        "Flow control": "Flow control",
        "Zprac. obrazu": "Zprac. obrazu",
        "Detekce": "Detekce",
        "Ukládání": "Ukladani",
        "Ukladani": "Ukladani",
        "Ukládání/overlay": "Ukladani/overlay",
        "Ukladani/overlay": "Ukladani/overlay",
        "Měření": "Mereni",
        "Mereni": "Mereni",
        "Geometrie": "Geometrie",
        "IO-Link": "IO-Link",
        "Obecné": "Obecne",
        "Obecne": "Obecne",
    }
    return mapping.get(token, token or "Obecne")


def _guess_category(filename: str) -> str:
    lowered = filename.lower()
    mapping = [
        ("trigger", "Flow control"),
        ("flow", "Flow control"),
        ("stop", "Flow control"),
        ("result_filter", "Flow control"),
        ("result_maker", "Flow control"),
        ("hdr", "Zprac. obrazu"),
        ("sobel", "Zprac. obrazu"),
        ("laplac", "Zprac. obrazu"),
        ("rozsireni", "Zprac. obrazu"),
        ("cut_on_detected", "Zprac. obrazu"),
        ("del_class", "Detekce"),
        ("save_image", "Ukladani"),
        ("logo", "Ukladani/overlay"),
        ("measure", "Mereni"),
        ("sjednoceni", "Geometrie"),
        ("unifier", "Geometrie"),
        ("majak", "IO-Link"),
        ("button", "IO-Link"),
        ("ifmdv", "IO-Link"),
    ]
    for token, category in mapping:
        if token in lowered:
            return category
    return "Obecne"


def _normalize_filename(filename: str) -> str:
    return filename.strip().lower()


def _extract_import_dependencies(text: str) -> str:
    modules = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            token = stripped.split("import ", 1)[1].split(" as ", 1)[0].split(",", 1)[0].strip()
            if token:
                modules.append(token.split(".", 1)[0])
        elif stripped.startswith("from "):
            token = stripped.split("from ", 1)[1].split(" import ", 1)[0].strip()
            if token:
                modules.append(token.split(".", 1)[0])
    unique = []
    for module in modules:
        if module not in unique:
            unique.append(module)
    return ", ".join(unique) if unique else "–"


def _extract_context_keys(text: str) -> str:
    keys = []
    for key in ("detectedRectangles", "result", "operatorInput", "image", "exit"):
        if key in text and key not in keys:
            keys.append(key)
    return ", ".join(keys) if keys else "–"


def _load_xlsx_rows(path: Path) -> List[List[str]]:
    ns_main = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    ns_rel = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    workbook_rel_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    rows: List[List[str]] = []
    with zipfile.ZipFile(path, "r") as archive:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root_shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in root_shared.findall("m:si", ns_main):
                parts = [node.text or "" for node in si.findall(".//m:t", ns_main)]
                shared_strings.append("".join(parts))

        root_workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        root_rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
            for rel in root_rels.findall("r:Relationship", ns_rel)
        }

        sheet_node = root_workbook.find("m:sheets/m:sheet", ns_main)
        if sheet_node is None:
            return rows
        rel_id = sheet_node.attrib.get(workbook_rel_key, "")
        sheet_target = rel_map.get(rel_id, "")
        if not sheet_target:
            return rows
        if not sheet_target.startswith("xl/"):
            sheet_target = f"xl/{sheet_target}"
        if sheet_target not in archive.namelist():
            return rows

        root_sheet = ET.fromstring(archive.read(sheet_target))
        for row_node in root_sheet.findall("m:sheetData/m:row", ns_main):
            row_values: List[str] = []
            for cell in row_node.findall("m:c", ns_main):
                cell_type = cell.attrib.get("t", "")
                inline_text = cell.find("m:is/m:t", ns_main)
                value_node = cell.find("m:v", ns_main)
                value = ""
                if inline_text is not None and inline_text.text is not None:
                    value = inline_text.text
                elif value_node is not None and value_node.text is not None:
                    raw = value_node.text
                    if cell_type == "s":
                        try:
                            value = shared_strings[int(raw)]
                        except Exception:
                            value = raw
                    else:
                        value = raw
                row_values.append(value.strip())
            if any(row_values):
                rows.append(row_values)
    return rows


def _extract_xlsx_metadata(path: Path) -> tuple[Dict[str, dict], List[str]]:
    rows = _load_xlsx_rows(path)
    if not rows:
        return {}, []

    header_index = None
    for idx, row in enumerate(rows):
        if row and row[0].strip().lower() == "soubor":
            header_index = idx
            break
    if header_index is None:
        return {}, []

    metadata: Dict[str, dict] = {}
    categories: List[str] = []
    for row in rows[header_index + 1 :]:
        if len(row) < 1:
            continue
        source_name = row[0].strip()
        if not source_name:
            continue
        purpose = row[2].strip() if len(row) > 2 else ""
        what_it_does = row[3].strip() if len(row) > 3 else ""
        context_keys = row[4].strip() if len(row) > 4 else ""
        dependencies = row[5].strip() if len(row) > 5 else ""
        category = _normalize_category(row[1].strip() if len(row) > 1 else "")
        if category and category not in categories:
            categories.append(category)

        short_description = purpose or what_it_does or f"Skript {source_name}"
        metadata[_normalize_filename(source_name)] = {
            "category": category or _guess_category(source_name),
            "purpose": purpose,
            "what_it_does": what_it_does or purpose,
            "context_keys": context_keys or "–",
            "dependencies": dependencies or "–",
            "short_description": short_description[:160],
            "description_source": "xlsx",
        }
    return metadata, categories


def _extract_popis_metadata(path: Path) -> Dict[str, dict]:
    text, _encoding = _read_text_with_fallback(path)
    sections: Dict[str, List[str]] = {}
    current_name = ""
    heading_pattern = re.compile(r"^[A-Za-z0-9_.\-]+\.txt$")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if heading_pattern.match(line):
            current_name = line
            sections[current_name] = []
            continue
        if current_name:
            sections[current_name].append(line)

    metadata: Dict[str, dict] = {}
    for name, lines in sections.items():
        if not lines:
            continue
        purpose = lines[0].strip()
        context_line = next((line for line in lines if line.lower().startswith("práce s kontextem:")), "")
        context_keys = context_line.split(":", 1)[1].strip() if ":" in context_line else "–"
        body = "\n".join(lines)
        dependencies = []
        if "vyžaduje requests" in body.lower() or "vyzaduje requests" in body.lower():
            dependencies.append("requests")
        inferred = _extract_import_dependencies(body)
        if inferred != "–":
            for token in inferred.split(","):
                cleaned = token.strip()
                if cleaned and cleaned not in dependencies:
                    dependencies.append(cleaned)

        metadata[_normalize_filename(name)] = {
            "category": _guess_category(name),
            "purpose": purpose,
            "what_it_does": purpose,
            "context_keys": context_keys if context_keys else "–",
            "dependencies": ", ".join(dependencies) if dependencies else "–",
            "short_description": purpose[:160],
            "description_source": "txt",
        }
    return metadata


def _generate_metadata(filename: str, text_preview: str) -> dict:
    description = _extract_description(text_preview, filename)
    return {
        "category": _guess_category(filename),
        "purpose": f"Skript {Path(filename).stem}",
        "what_it_does": description,
        "context_keys": _extract_context_keys(text_preview),
        "dependencies": _extract_import_dependencies(text_preview),
        "short_description": description,
        "description_source": "generated",
    }


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
            self.save_categories(DEFAULT_CATEGORY_ORDER)
        if not self.catalog_path.exists():
            self.save_catalog(ScriptCatalogIndex(schema_version=SCHEMA_VERSION, generated_at=_utc_now(), items=[]))

    def save_categories(self, categories: List[str]) -> None:
        ordered = []
        for category in categories:
            normalized = _normalize_category(category)
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        if not ordered:
            ordered = list(DEFAULT_CATEGORY_ORDER)
        self.categories_path.write_text(
            json.dumps({"schema_version": "1.0", "categories": ordered}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

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

    def _clear_directory(self, path: Path) -> None:
        if not path.exists():
            return
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

    def _load_metadata(self, source_dir: Path) -> tuple[Dict[str, dict], List[str]]:
        metadata: Dict[str, dict] = {}
        categories: List[str] = []

        xlsx_candidates = sorted(source_dir.glob("*.xlsx"), key=lambda item: item.name.lower())
        if xlsx_candidates:
            xlsx_meta, xlsx_categories = _extract_xlsx_metadata(xlsx_candidates[0])
            metadata.update(xlsx_meta)
            categories.extend(xlsx_categories)

        popis_candidates = sorted(
            [path for path in source_dir.glob("*.txt") if path.name.lower().startswith("popis funkcionalit")],
            key=lambda item: item.name.lower(),
        )
        if popis_candidates:
            popis_meta = _extract_popis_metadata(popis_candidates[0])
            for key, value in popis_meta.items():
                if key in metadata:
                    merged = dict(value)
                    merged.update(metadata[key])
                    metadata[key] = merged
                else:
                    metadata[key] = value
        return metadata, categories

    def _next_unique_id(self, base_slug: str, used_ids: set[str]) -> str:
        candidate = base_slug
        index = 2
        while candidate in used_ids:
            candidate = f"{base_slug}_{index}"
            index += 1
        used_ids.add(candidate)
        return candidate

    def _build_asset_from_file(self, source_file: Path, metadata: dict, used_ids: set[str]) -> ScriptAsset:
        ext = source_file.suffix.lower()
        format_name = "pmodule" if ext == ".pmodule" else ("py" if ext == ".py" else "txt")
        source_bytes = source_file.read_bytes()
        source_hash = hashlib.sha256(source_bytes).hexdigest()
        slug = _slugify(source_file.stem)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        unique_id = self._next_unique_id(f"{slug}_{timestamp}", used_ids)

        raw_name = f"{unique_id}{ext}"
        raw_target = self.scripts_raw_dir / raw_name
        shutil.copy2(source_file, raw_target)

        text_preview = ""
        encoding_source = "binary"
        utf8_target = ""
        is_empty = len(source_bytes) == 0
        if format_name != "pmodule":
            text_preview, encoding_source = _read_text_with_fallback(source_file)
            utf8_name = f"{unique_id}.txt"
            utf8_target_path = self.scripts_utf8_dir / utf8_name
            utf8_target_path.write_text(text_preview, encoding="utf-8")
            utf8_target = (Path("scripts_utf8") / utf8_name).as_posix()
        else:
            pmodule_target = self.pmodule_dir / f"{unique_id}.pmodule"
            shutil.copy2(source_file, pmodule_target)

        enriched = dict(metadata) if metadata else _generate_metadata(source_file.name, text_preview)
        if not enriched:
            enriched = _generate_metadata(source_file.name, text_preview)
        category = _normalize_category(str(enriched.get("category", "") or _guess_category(source_file.name)))
        short_description = str(
            enriched.get("short_description", "") or _extract_description(text_preview, source_file.name)
        )

        tags = [category, format_name]
        now = _utc_now()
        return ScriptAsset(
            id=unique_id,
            name=source_file.stem,
            source_filename=source_file.name,
            storage_path_utf8=utf8_target,
            storage_path_raw=(Path("scripts_raw") / raw_name).as_posix(),
            format=format_name,  # type: ignore[arg-type]
            category=category,
            tags=tags,
            short_description=short_description[:160],
            encoding_source=encoding_source,
            size_bytes=len(source_bytes),
            sha256=source_hash,
            created_at=now,
            updated_at=now,
            empty=is_empty,
            purpose=str(enriched.get("purpose", "")).strip(),
            what_it_does=str(enriched.get("what_it_does", "")).strip(),
            context_keys=str(enriched.get("context_keys", "–") or "–").strip(),
            dependencies=str(enriched.get("dependencies", "–") or "–").strip(),
            description_source=str(enriched.get("description_source", "generated") or "generated"),
        )

    def replace_from_folder(self, source_dir: Path, skip_empty: bool = True) -> tuple[ScriptCatalogIndex, int, int]:
        self.ensure_structure()
        source_dir = Path(source_dir)
        if not source_dir.exists():
            raise FileNotFoundError(f"Source folder not found: {source_dir}")

        metadata_map, xlsx_categories = self._load_metadata(source_dir)

        self._clear_directory(self.scripts_raw_dir)
        self._clear_directory(self.scripts_utf8_dir)
        self._clear_directory(self.pmodule_dir)

        assets: List[ScriptAsset] = []
        used_ids: set[str] = set()
        skipped_empty = 0
        imported_count = 0
        for file_path in sorted(source_dir.iterdir(), key=lambda item: item.name.lower()):
            if not file_path.is_file():
                continue
            lowered_name = file_path.name.lower()
            if lowered_name.startswith("popis funkcionalit"):
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            source_bytes = file_path.read_bytes()
            if skip_empty and len(source_bytes) == 0:
                skipped_empty += 1
                continue

            key = _normalize_filename(file_path.name)
            text_preview = ""
            if file_path.suffix.lower() != ".pmodule":
                text_preview, _enc = _read_text_with_fallback(file_path)
            metadata = metadata_map.get(key) or _generate_metadata(file_path.name, text_preview)
            asset = self._build_asset_from_file(file_path, metadata, used_ids)
            assets.append(asset)
            imported_count += 1

        categories_seen = set(xlsx_categories)
        categories_seen.update(asset.category for asset in assets)
        ordered_categories = [cat for cat in DEFAULT_CATEGORY_ORDER if cat in categories_seen]
        extra_categories = sorted(cat for cat in categories_seen if cat not in ordered_categories)
        self.save_categories(ordered_categories + extra_categories)

        catalog = ScriptCatalogIndex(schema_version=SCHEMA_VERSION, generated_at=_utc_now(), items=assets)
        self.save_catalog(catalog)
        return catalog, imported_count, skipped_empty

    def import_from_folder(self, source_dir: Path) -> ScriptCatalogIndex:
        catalog, _imported, _skipped_empty = self.replace_from_folder(source_dir, skip_empty=False)
        return catalog

    def list_assets(self, search: str = "", category: str = "all") -> List[ScriptAsset]:
        catalog = self.load_catalog()
        search_term = search.strip().lower()
        selected = []
        for asset in catalog.items:
            if category and category.lower() != "all" and asset.category.lower() != category.lower():
                continue
            blob = " ".join(
                [
                    asset.name,
                    asset.source_filename,
                    asset.short_description,
                    asset.purpose,
                    asset.what_it_does,
                    asset.context_keys,
                    asset.dependencies,
                    " ".join(asset.tags),
                ]
            ).lower()
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
        categories = [str(item) for item in (payload.get("categories") or []) if str(item).strip()]
        seen = set(categories)
        extra = []
        for asset in self.load_catalog().items:
            if asset.category not in seen:
                seen.add(asset.category)
                extra.append(asset.category)
        return categories + sorted(extra)
