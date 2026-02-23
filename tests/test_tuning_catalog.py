from __future__ import annotations

from html import escape
from pathlib import Path
import zipfile

from pektool.core.tuning_catalog import TuningCatalog


def _build_test_xlsx(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet_rows = []
    for idx, row in enumerate(rows, start=1):
        cells = []
        for value in row:
            cells.append(f"<c t=\"inlineStr\"><is><t>{escape(value)}</t></is></c>")
        sheet_rows.append(f"<row r=\"{idx}\">{''.join(cells)}</row>")
    sheet_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<sheetData>"
        f"{''.join(sheet_rows)}"
        "</sheetData>"
        "</worksheet>"
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
                "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                "<Override PartName=\"/xl/workbook.xml\" "
                "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
                "<Override PartName=\"/xl/worksheets/sheet1.xml\" "
                "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
                "</Types>"
            ),
        )
        archive.writestr(
            "_rels/.rels",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                "<Relationship Id=\"rId1\" "
                "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
                "Target=\"xl/workbook.xml\"/>"
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
                "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
                "<sheets><sheet name=\"List1\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
                "</workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
                "<Relationship Id=\"rId1\" "
                "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" "
                "Target=\"worksheets/sheet1.xml\"/>"
                "</Relationships>"
            ),
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def test_replace_from_folder_deletes_old_assets_and_skips_empty(tmp_path):
    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")

    old_source = tmp_path / "old"
    old_source.mkdir()
    (old_source / "OLD.txt").write_text("print('old')", encoding="utf-8")
    catalog.import_from_folder(old_source)

    new_source = tmp_path / "new"
    new_source.mkdir()
    (new_source / "AI_TRIGGER_V06_TESTED.txt").write_text("print('new')", encoding="utf-8")
    (new_source / "PYZBAR_BARCODE_READER.txt").write_text("", encoding="utf-8")

    result, imported, skipped_empty = catalog.replace_from_folder(new_source, skip_empty=True)
    assert imported == 1
    assert skipped_empty == 1
    assert len(result.items) == 1
    assert result.items[0].source_filename == "AI_TRIGGER_V06_TESTED.txt"
    assert "OLD.txt" not in [item.source_filename for item in result.items]


def test_manual_override_metadata_is_used_for_pyzbar(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "PYZBAR_BARCODE_READER.txt").write_text(
        "import cv2\nimport numpy as np\nimport pyzbar.pyzbar as zbar\n\ndef main(context):\n    pass\n",
        encoding="utf-8",
    )

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    result, imported, skipped_empty = catalog.replace_from_folder(source, skip_empty=True)
    assert imported == 1
    assert skipped_empty == 0

    asset = result.items[0]
    assert asset.source_filename == "PYZBAR_BARCODE_READER.txt"
    assert asset.category == "Detekce"
    assert asset.purpose == "Dekodovani carovych a 2D kodu pomoci pyzbar"
    assert "context['barcode']" in asset.what_it_does
    assert asset.context_keys == "image, barcode, barcode_debug"
    assert asset.dependencies == "pyzbar, cv2, numpy"
    assert asset.description_source == "manual"


def test_non_empty_pyzbar_is_imported_when_skip_empty_enabled(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "PYZBAR_BARCODE_READER.txt").write_text("print('barcode')\n", encoding="utf-8")
    (source / "EMPTY_SCRIPT.txt").write_text("", encoding="utf-8")

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    result, imported, skipped_empty = catalog.replace_from_folder(source, skip_empty=True)
    assert imported == 1
    assert skipped_empty == 1
    assert any(item.source_filename == "PYZBAR_BARCODE_READER.txt" for item in result.items)


def test_metadata_from_xlsx_is_applied_to_asset(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "AI_TRIGGER_V06_TESTED.txt").write_text("print('x')", encoding="utf-8")

    _build_test_xlsx(
        source / "prehlad.xlsx",
        [
            ["ignored"],
            ["Soubor", "Kategorie", "K čemu slouží", "Co dělá", "Klíčové context", "Závislosti"],
            [
                "AI_TRIGGER_V06_TESTED.txt",
                "Flow control",
                "Gate flow",
                "Debounce and gating",
                "result, exit",
                "–",
            ],
        ],
    )

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    result, imported, skipped_empty = catalog.replace_from_folder(source, skip_empty=True)
    assert imported == 1
    assert skipped_empty == 0

    asset = result.items[0]
    assert asset.category == "Flow control"
    assert asset.purpose == "Gate flow"
    assert asset.what_it_does == "Debounce and gating"
    assert asset.context_keys == "result, exit"
    assert asset.dependencies == "–"
    assert asset.description_source == "xlsx"


def test_missing_metadata_is_generated(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "CUSTOM_SCRIPT.txt").write_text(
        "import requests\n\ndef main(context):\n    context['result'] = True\n",
        encoding="utf-8",
    )

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    result, imported, skipped_empty = catalog.replace_from_folder(source, skip_empty=True)
    assert imported == 1
    assert skipped_empty == 0

    asset = result.items[0]
    assert asset.description_source == "generated"
    assert asset.purpose.startswith("Skript CUSTOM_SCRIPT")
    assert "result" in asset.context_keys
    assert "requests" in asset.dependencies


def test_replace_handles_cp1250_and_creates_utf8_copy(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    phrase = "Příliš žluťoučký kůň"
    (source / "cp1250_script.txt").write_bytes(phrase.encode("cp1250"))

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    result, imported, skipped_empty = catalog.replace_from_folder(source, skip_empty=False)
    assert imported == 1
    assert skipped_empty == 0

    asset = result.items[0]
    assert asset.encoding_source == "cp1250"
    utf8_path = catalog.root / asset.storage_path_utf8
    assert phrase in utf8_path.read_text(encoding="utf-8")
