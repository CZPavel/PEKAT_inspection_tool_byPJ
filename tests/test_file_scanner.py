from pathlib import Path

from pektool.io.file_scanner import FileScanner


def test_file_scanner_stability(tmp_path: Path):
    image = tmp_path / "a.png"
    image.write_bytes(b"test")

    scanner = FileScanner(
        folder=tmp_path,
        include_subfolders=False,
        extensions=[".png"],
        stability_checks=1,
        logger=__import__("logging").getLogger("test"),
    )

    first = scanner.scan()
    assert first == []

    second = scanner.scan()
    assert image in second