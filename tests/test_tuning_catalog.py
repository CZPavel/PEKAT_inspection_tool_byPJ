from pathlib import Path

from pektool.core.tuning_catalog import TuningCatalog


def test_catalog_import_detects_encodings_utf8_cp1250(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "utf8_script.txt").write_text("# Hello world", encoding="utf-8")
    (source / "cp1250_script.txt").write_bytes("Příliš žluťoučký kůň".encode("cp1250"))

    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    index = catalog.import_from_folder(source)
    assert len(index.items) == 2
    encodings = {item.source_filename: item.encoding_source for item in index.items}
    assert encodings["utf8_script.txt"] in {"utf-8", "utf-8-sig"}
    assert encodings["cp1250_script.txt"] == "cp1250"


def test_catalog_creates_utf8_canonical_and_raw_copy(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "A.txt").write_bytes("Žluťoučký".encode("cp1250"))
    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    index = catalog.import_from_folder(source)
    item = index.items[0]
    raw_path = catalog.root / item.storage_path_raw
    utf8_path = catalog.root / item.storage_path_utf8
    assert raw_path.exists()
    assert utf8_path.exists()
    assert "Žluťoučký" in utf8_path.read_text(encoding="utf-8")


def test_catalog_extracts_description_from_header(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "test.py").write_text("# Important header description\nprint('x')", encoding="utf-8")
    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    index = catalog.import_from_folder(source)
    assert index.items[0].short_description.startswith("Important header")


def test_catalog_handles_empty_files(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "empty.txt").write_text("", encoding="utf-8")
    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    index = catalog.import_from_folder(source)
    assert index.items[0].empty is True
    assert index.items[0].short_description == "Empty script file."


def test_catalog_includes_pmodule_metadata_only(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "module.pmodule").write_bytes(b"PMODULEDATA")
    catalog = TuningCatalog(tmp_path / "resources" / "code_modules")
    index = catalog.import_from_folder(source)
    item = index.items[0]
    assert item.format == "pmodule"
    assert item.storage_path_utf8 == ""
    assert (catalog.root / item.storage_path_raw).exists()
