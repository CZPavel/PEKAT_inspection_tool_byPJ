from pektool.core import port_info


def test_known_ports_contains_1947():
    entries = port_info.get_known_pekat_ports()
    ports = {entry.port for entry in entries}
    assert "1947" in ports
    assert "7000" in ports
    assert "7002" in ports
    assert "8000-8100" in ports


def test_parse_get_nettcpconnection_json():
    raw = '[{"LocalPort":7000,"OwningProcess":100},{"LocalPort":8000,"OwningProcess":200}]'
    parsed = port_info.parse_get_nettcpconnection_json(raw)
    assert parsed == {7000: 100, 8000: 200}


def test_parse_netstat_output():
    raw = """
  TCP    0.0.0.0:7000           0.0.0.0:0              LISTENING       1111
  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       2222
  TCP    127.0.0.1:9000         0.0.0.0:0              ESTABLISHED     3333
"""
    parsed = port_info.parse_netstat_output(raw)
    assert parsed == {7000: 1111, 8000: 2222}


def test_classify_port_pm_and_project():
    allocated, _detail = port_info.classify_port(
        port=7000,
        pid=101,
        process_name="pekat-manager",
        pm_projects=[],
        pm_http_ok=True,
        pm_tcp_ok=False,
        ping_ok=False,
    )
    assert allocated == "PEKAT PM HTTP"

    allocated, _detail = port_info.classify_port(
        port=8010,
        pid=303,
        process_name="python",
        pm_projects=[{"port": 8010, "status": "Running"}],
        pm_http_ok=True,
        pm_tcp_ok=False,
        ping_ok=False,
    )
    assert allocated == "PEKAT project"


def test_scan_port_range_uses_check_ports(monkeypatch):
    captured = {}

    def fake_check_ports(ports, host, pm_base_url, include_closed):
        captured["ports"] = list(ports)
        captured["host"] = host
        captured["pm_base_url"] = pm_base_url
        captured["include_closed"] = include_closed
        return [
            port_info.PortScanResult(
                port=8000,
                listening=True,
                pid=1,
                process_name="pekat",
                allocated_by="PEKAT related",
                detail="mock",
            )
        ]

    monkeypatch.setattr(port_info, "check_ports", fake_check_ports)
    results = port_info.scan_port_range(8000, 8002)
    assert captured["ports"] == [8000, 8001, 8002]
    assert captured["include_closed"] is False
    assert len(results) == 1
    assert results[0].port == 8000


def test_check_ports_handles_pm_fetch_failure(monkeypatch):
    monkeypatch.setattr(
        port_info,
        "scan_local_listeners",
        lambda: {
            1947: port_info.ListenerInfo(port=1947, pid=555, process_name="customsvc.exe"),
        },
    )
    monkeypatch.setattr(port_info, "fetch_pm_projects_list", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(port_info, "probe_pm_tcp", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(port_info, "probe_ping", lambda *_args, **_kwargs: False)

    results = port_info.check_ports([1947], include_closed=True)
    assert len(results) == 1
    assert results[0].port == 1947
    assert results[0].listening is True
    assert results[0].allocated_by in {"Other", "PEKAT related", "Unknown"}


def test_get_basic_network_info_from_powershell(monkeypatch):
    ps_payload = (
        '[{"InterfaceAlias":"Ethernet","MacAddress":"AA-BB-CC-DD-EE-FF",'
        '"NetworkName":"FactoryLAN","IPv4Address":[{"IPAddress":"192.168.1.25","PrefixLength":24}]}]'
    )
    monkeypatch.setattr(port_info, "_run_powershell", lambda *_args, **_kwargs: ps_payload)

    text = port_info.get_basic_network_info()
    assert "Adapter: Ethernet" in text
    assert "Network: FactoryLAN" in text
    assert "MAC: AA-BB-CC-DD-EE-FF" in text
    assert "IPv4/Subnet: 192.168.1.25 / 255.255.255.0" in text
