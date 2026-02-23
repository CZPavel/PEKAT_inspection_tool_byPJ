import os
import time

import pytest

if os.environ.get("PEKTOOL_QT_TESTS") != "1":
    pytest.skip("Qt GUI tests are opt-in via PEKTOOL_QT_TESTS=1", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from pektool.core.port_info import NetworkAdapterInfo, PortScanResult
from pektool.gui.main import MainWindow


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app
    app.closeAllWindows()
    app.quit()


def _wait_for_scan(window: MainWindow, app: QtWidgets.QApplication, timeout_sec: float = 3.0) -> None:
    start = time.time()
    while window.port_scan_running and (time.time() - start) < timeout_sec:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def _wait_for_network_load(
    window: MainWindow, app: QtWidgets.QApplication, timeout_sec: float = 3.0
) -> None:
    start = time.time()
    while window.network_info_loading and (time.time() - start) < timeout_sec:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def test_pekat_info_tab_exists(qapp):
    window = MainWindow()
    try:
        tab_names = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert "Pekat Info" in tab_names
    finally:
        window.close()


def test_pekat_info_network_cards_use_compact_spacing(qapp):
    window = MainWindow()
    try:
        assert window.network_cards_layout.horizontalSpacing() == 10
        assert window.network_cards_layout.verticalSpacing() == 6
        policy = window.network_cards_scroll.parentWidget().sizePolicy()
        assert policy.verticalPolicy() == QtWidgets.QSizePolicy.Expanding
        scroll_areas = window.pekat_info_tab.findChildren(QtWidgets.QScrollArea)
        assert scroll_areas
    finally:
        window.close()


def test_pekat_info_common_scan_populates(monkeypatch, qapp):
    window = MainWindow()
    try:
        monkeypatch.setattr(
            "pektool.gui.main.check_ports",
            lambda *_args, **_kwargs: [
                PortScanResult(
                    port=7000,
                    listening=True,
                    pid=100,
                    process_name="pekat_pm.exe",
                    allocated_by="PEKAT PM HTTP",
                    detail="ok",
                ),
                PortScanResult(
                    port=7002,
                    listening=False,
                    pid=None,
                    process_name="",
                    allocated_by="Unknown",
                    detail="closed",
                ),
                PortScanResult(
                    port=8000,
                    listening=True,
                    pid=200,
                    process_name="pekat_project.exe",
                    allocated_by="PEKAT project",
                    detail="ok",
                ),
                PortScanResult(
                    port=1947,
                    listening=True,
                    pid=300,
                    process_name="licsvc.exe",
                    allocated_by="Other",
                    detail="in use",
                ),
            ],
        )
        monkeypatch.setattr(
            "pektool.gui.main.scan_port_range",
            lambda *_args, **_kwargs: [
                PortScanResult(
                    port=8001,
                    listening=True,
                    pid=201,
                    process_name="python.exe",
                    allocated_by="Other",
                    detail="occupied",
                )
            ],
        )

        window._check_common_ports()
        _wait_for_scan(window, qapp)

        assert "Done" in window.port_scan_status_label.text()
        assert window.port_scan_table.rowCount() >= 1
        row_1947 = window.known_port_row_map["1947"][0]
        status_item = window.common_ports_table.item(row_1947, 3)
        assert status_item is not None
    finally:
        window.close()


def test_pekat_info_links_present(qapp):
    window = MainWindow()
    try:
        labels = window.pekat_info_tab.findChildren(QtWidgets.QLabel)
        links = [label.text() for label in labels if "href=" in label.text()]
        assert any("pekatvision.com" in link for link in links)
        assert any("github.com/pekat-vision" in link for link in links)
    finally:
        window.close()


def test_network_info_loaded_on_tab_open(monkeypatch, qapp):
    window = MainWindow()
    try:
        monkeypatch.setattr(
            "pektool.gui.main.get_network_adapters_info",
            lambda: [
                NetworkAdapterInfo(
                    adapter_name="Ethernet 1",
                    mac_address="AA-BB-CC-DD-EE-FF",
                    network_name="FactoryLAN",
                    ipv4_with_masks=["192.168.0.10 / 255.255.255.0"],
                ),
                NetworkAdapterInfo(
                    adapter_name="Wi-Fi",
                    mac_address="11-22-33-44-55-66",
                    network_name="OfficeWifi",
                    ipv4_with_masks=["10.0.0.15 / 255.255.255.0"],
                ),
            ],
        )
        tab_index = [window.tabs.tabText(i) for i in range(window.tabs.count())].index("Pekat Info")
        window.tabs.setCurrentIndex(tab_index)
        _wait_for_network_load(window, qapp)
        cards = [box for box in window.network_cards_container.findChildren(QtWidgets.QGroupBox) if box.title()]
        assert any(card.title() == "Ethernet 1" for card in cards)
        assert cards[-1].title() == "Wi-Fi"
    finally:
        window.close()
