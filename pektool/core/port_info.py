from __future__ import annotations

import csv
import json
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from io import StringIO
from typing import Any, Dict, Iterable, List, Optional

import requests


@dataclass
class KnownPortEntry:
    port: str
    purpose: str
    link: str


@dataclass
class ListenerInfo:
    port: int
    pid: Optional[int]
    process_name: str


@dataclass
class PortScanResult:
    port: int
    listening: bool
    pid: Optional[int]
    process_name: str
    allocated_by: str
    detail: str


@dataclass
class NetworkAdapterInfo:
    adapter_name: str
    mac_address: str
    network_name: str
    ipv4_with_masks: List[str]


def get_known_pekat_ports() -> List[KnownPortEntry]:
    return [
        KnownPortEntry(
            port="7000",
            purpose="Projects Manager HTTP project list",
            link="http://127.0.0.1:7000/projects/list",
        ),
        KnownPortEntry(
            port="7000",
            purpose="Projects Manager UI",
            link="http://127.0.0.1:7000",
        ),
        KnownPortEntry(
            port="7002",
            purpose="Projects Manager TCP control (if enabled)",
            link="https://pekatvision.atlassian.net/wiki/spaces/KB34/pages/1207109343/Simple+TCP+communications",
        ),
        KnownPortEntry(
            port="8000",
            purpose="Project typical API (test page)",
            link="http://localhost:8000/api",
        ),
        KnownPortEntry(
            port="8000",
            purpose="Project typical root",
            link="http://localhost:8000",
        ),
        KnownPortEntry(
            port="8000-8100",
            purpose="Project port scan range",
            link="https://pekatvision.atlassian.net/wiki/spaces/KB34/pages/1207107616/PEKAT+VISION+Knowledge+base+3.19+Home",
        ),
        KnownPortEntry(
            port="1947",
            purpose="Licensing/Update port (user-defined for this setup)",
            link="http://localhost:1947",
        ),
    ]


def parse_get_nettcpconnection_json(raw_json: str) -> Dict[int, int]:
    raw_json = (raw_json or "").strip()
    if not raw_json:
        return {}
    payload = json.loads(raw_json)
    rows = payload if isinstance(payload, list) else [payload]
    result: Dict[int, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            port = int(row.get("LocalPort"))
            pid = int(row.get("OwningProcess"))
        except (TypeError, ValueError):
            continue
        result[port] = pid
    return result


def parse_netstat_output(raw_text: str) -> Dict[int, int]:
    result: Dict[int, int] = {}
    pattern = re.compile(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE)
    for line in (raw_text or "").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        try:
            port = int(match.group(1))
            pid = int(match.group(2))
        except ValueError:
            continue
        result[port] = pid
    return result


def _run_powershell(command: str, timeout: float = 6.0) -> str:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "PowerShell command failed")
    return completed.stdout


def _get_process_map_powershell() -> Dict[int, str]:
    raw = _run_powershell(
        "Get-Process | Select-Object -Property Id,ProcessName | ConvertTo-Json -Compress",
        timeout=8.0,
    )
    payload = json.loads((raw or "").strip() or "[]")
    rows = payload if isinstance(payload, list) else [payload]
    process_map: Dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            pid = int(row.get("Id"))
        except (TypeError, ValueError):
            continue
        name = str(row.get("ProcessName") or "")
        process_map[pid] = name
    return process_map


def _get_process_map_tasklist() -> Dict[int, str]:
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        timeout=8.0,
    )
    if completed.returncode != 0:
        return {}
    process_map: Dict[int, str] = {}
    reader = csv.reader(StringIO(completed.stdout))
    for row in reader:
        if len(row) < 2:
            continue
        name = row[0].strip()
        pid_text = row[1].strip().replace(",", "")
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        process_map[pid] = name
    return process_map


def resolve_process_name(pid: Optional[int], process_map: Optional[Dict[int, str]] = None) -> str:
    if pid is None:
        return ""
    if process_map is not None:
        return process_map.get(pid, "")
    try:
        mapping = _get_process_map_powershell()
    except Exception:
        mapping = _get_process_map_tasklist()
    return mapping.get(pid, "")


def scan_local_listeners() -> Dict[int, ListenerInfo]:
    port_to_pid: Dict[int, int] = {}
    try:
        raw = _run_powershell(
            "Get-NetTCPConnection -State Listen | Select-Object -Property LocalPort,OwningProcess | ConvertTo-Json -Compress"
        )
        port_to_pid = parse_get_nettcpconnection_json(raw)
    except Exception:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
        port_to_pid = parse_netstat_output(completed.stdout if completed.returncode == 0 else "")

    try:
        process_map = _get_process_map_powershell()
    except Exception:
        process_map = _get_process_map_tasklist()

    listeners: Dict[int, ListenerInfo] = {}
    for port, pid in port_to_pid.items():
        listeners[port] = ListenerInfo(
            port=port,
            pid=pid,
            process_name=resolve_process_name(pid, process_map=process_map),
        )
    return listeners


def fetch_pm_projects_list(base_url: str = "http://127.0.0.1:7000", timeout_sec: float = 2.0) -> List[Dict[str, Any]]:
    response = requests.get(f"{base_url.rstrip('/')}/projects/list", timeout=timeout_sec)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        nested = payload.get("projects")
        if isinstance(nested, list):
            return nested
    return []


def probe_ping(port: int, host: str = "127.0.0.1", timeout_sec: float = 1.5) -> bool:
    try:
        response = requests.get(f"http://{host}:{port}/ping", timeout=timeout_sec)
        return response.status_code == 200
    except requests.RequestException:
        return False


def probe_pm_tcp(port: int = 7002, host: str = "127.0.0.1", timeout_sec: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec) as sock:
            sock.settimeout(timeout_sec)
            sock.sendall(b"status:C:\\__no_such_project__\n")
            data = sock.recv(128)
    except OSError:
        return False
    text = data.decode("utf-8", errors="ignore").strip().lower()
    markers = [
        "not-found",
        "unknown command",
        "unknown-command",
        "invalid-command",
        "stopped",
        "stopping",
        "starting",
        "running",
        "done",
        "error:port",
    ]
    return any(marker in text for marker in markers)


def _project_port_match(pm_projects: List[Dict[str, Any]], port: int) -> bool:
    for item in pm_projects:
        if not isinstance(item, dict):
            continue
        try:
            item_port = int(item.get("port"))
        except (TypeError, ValueError):
            continue
        if item_port != port:
            continue
        status = str(item.get("status", "")).strip().lower()
        if status in {"running", "starting", "stopping"} or not status:
            return True
    return False


def classify_port(
    port: int,
    pid: Optional[int],
    process_name: str,
    pm_projects: List[Dict[str, Any]],
    pm_http_ok: bool,
    pm_tcp_ok: bool,
    ping_ok: bool,
) -> tuple[str, str]:
    process_lower = (process_name or "").lower()

    if port == 7000 and pm_http_ok:
        return "PEKAT PM HTTP", "Projects Manager HTTP endpoint responded."

    if port == 7002 and pm_tcp_ok:
        return "PEKAT PM TCP", "Projects Manager TCP probe responded."

    if _project_port_match(pm_projects, port):
        return "PEKAT project", "Port matches running project in Projects Manager list."

    if ping_ok:
        return "PEKAT project/API likely", "Ping endpoint responded."

    if "pekat" in process_lower:
        return "PEKAT related", f"Process name suggests PEKAT: {process_name}"

    if pid is not None or process_name:
        return "Other", f"Listening process: {process_name or 'PID ' + str(pid)}"

    return "Unknown", "No reliable ownership signal."


def check_ports(
    ports: Iterable[int],
    host: str = "127.0.0.1",
    pm_base_url: str = "http://127.0.0.1:7000",
    include_closed: bool = True,
) -> List[PortScanResult]:
    target_ports = sorted({int(p) for p in ports})
    listeners = scan_local_listeners()

    try:
        pm_projects = fetch_pm_projects_list(pm_base_url)
        pm_http_ok = True
    except Exception:
        pm_projects = []
        pm_http_ok = False

    pm_tcp_ok = False
    if 7002 in listeners or 7002 in target_ports:
        pm_tcp_ok = probe_pm_tcp(7002, host=host)

    results: List[PortScanResult] = []
    for port in target_ports:
        listener = listeners.get(port)
        if listener is None:
            if include_closed:
                results.append(
                    PortScanResult(
                        port=port,
                        listening=False,
                        pid=None,
                        process_name="",
                        allocated_by="Unknown",
                        detail="No listener on local host.",
                    )
                )
            continue

        ping_ok = probe_ping(port, host=host)
        allocated_by, detail = classify_port(
            port=port,
            pid=listener.pid,
            process_name=listener.process_name,
            pm_projects=pm_projects,
            pm_http_ok=pm_http_ok,
            pm_tcp_ok=pm_tcp_ok,
            ping_ok=ping_ok,
        )
        results.append(
            PortScanResult(
                port=port,
                listening=True,
                pid=listener.pid,
                process_name=listener.process_name,
                allocated_by=allocated_by,
                detail=detail,
            )
        )

    return results


def scan_port_range(
    start: int = 8000,
    end: int = 8100,
    host: str = "127.0.0.1",
    pm_base_url: str = "http://127.0.0.1:7000",
) -> List[PortScanResult]:
    ports = range(int(start), int(end) + 1)
    return check_ports(ports, host=host, pm_base_url=pm_base_url, include_closed=False)


def _prefix_to_mask(prefix: int) -> str:
    prefix = max(0, min(32, int(prefix)))
    mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix > 0 else 0
    return ".".join(str((mask >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _extract_ipv4_entries(value: Any) -> List[tuple[str, Optional[int]]]:
    entries: List[tuple[str, Optional[int]]] = []
    if value is None:
        return entries

    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, dict):
            ip = str(item.get("IPAddress") or item.get("Address") or "").strip()
            prefix_raw = item.get("PrefixLength")
            prefix: Optional[int] = None
            if prefix_raw is not None:
                try:
                    prefix = int(prefix_raw)
                except (TypeError, ValueError):
                    prefix = None
            if ip:
                entries.append((ip, prefix))
        else:
            text = str(item).strip()
            if text:
                entries.append((text, None))
    return entries


def _parse_ipconfig_adapters(text: str) -> List[NetworkAdapterInfo]:
    adapters: List[NetworkAdapterInfo] = []
    blocks = re.split(r"\r?\n\r?\n", text or "")

    for block in blocks:
        raw_lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not raw_lines:
            continue
        header = raw_lines[0].strip()
        if ":" not in header:
            continue

        adapter_name = header.rstrip(":").replace("adapter", "").strip()
        ipv4 = "-"
        subnet = "-"
        mac = "-"
        network_name = "-"

        for line in raw_lines[1:]:
            if ":" not in line:
                continue
            left, right = line.split(":", 1)
            key = left.strip().lower()
            value = right.strip()
            if "physical address" in key:
                mac = value
            elif "ipv4 address" in key:
                ipv4 = value.replace("(Preferred)", "").strip()
            elif "subnet mask" in key:
                subnet = value
            elif "dns suffix" in key and value:
                network_name = value

        if ipv4 == "-" and mac == "-" and subnet == "-" and network_name == "-":
            continue
        ip_items = []
        if ipv4 != "-" and subnet != "-":
            ip_items.append(f"{ipv4} / {subnet}")
        elif ipv4 != "-":
            ip_items.append(f"{ipv4} / -")
        adapters.append(
            NetworkAdapterInfo(
                adapter_name=adapter_name or "Unknown",
                mac_address=mac,
                network_name=network_name,
                ipv4_with_masks=ip_items,
            )
        )
    return adapters


def _build_network_adapter_items_from_rows(rows: List[Dict[str, Any]]) -> List[NetworkAdapterInfo]:
    adapters: List[NetworkAdapterInfo] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        alias = str(row.get("InterfaceAlias") or "Unknown").strip()
        network_name = str(row.get("NetworkName") or "-").strip() or "-"
        mac_address = str(row.get("MacAddress") or "-").strip() or "-"
        ipv4_entries = _extract_ipv4_entries(row.get("IPv4Address"))
        formatted_ipv4 = []
        for ip_address, prefix in ipv4_entries:
            subnet_mask = _prefix_to_mask(prefix) if prefix is not None else "-"
            formatted_ipv4.append(f"{ip_address} / {subnet_mask}")
        if not formatted_ipv4:
            formatted_ipv4 = ["- / -"]
        adapters.append(
            NetworkAdapterInfo(
                adapter_name=alias,
                mac_address=mac_address,
                network_name=network_name,
                ipv4_with_masks=formatted_ipv4,
            )
        )
    return adapters


def get_network_adapters_info() -> List[NetworkAdapterInfo]:
    try:
        raw = _run_powershell(
            "$profiles=@{}; Get-NetConnectionProfile | ForEach-Object { $profiles[$_.InterfaceAlias]=$_.Name }; "
            "$adapters=@{}; Get-NetAdapter | ForEach-Object { $adapters[$_.InterfaceAlias]=$_.MacAddress }; "
            "Get-NetIPConfiguration | ForEach-Object { "
            "$ipv4=@($_.IPv4Address | ForEach-Object { [PSCustomObject]@{ IPAddress=$_.IPAddress; PrefixLength=$_.PrefixLength } }); "
            "[PSCustomObject]@{ InterfaceAlias=$_.InterfaceAlias; MacAddress=$adapters[$_.InterfaceAlias]; NetworkName=$profiles[$_.InterfaceAlias]; IPv4Address=$ipv4 } "
            "} | "
            "ConvertTo-Json -Depth 6",
            timeout=8.0,
        )
        payload = json.loads((raw or "").strip() or "[]")
        rows = payload if isinstance(payload, list) else [payload]
        adapters = _build_network_adapter_items_from_rows(rows)
        if adapters:
            return adapters
    except Exception:
        pass

    try:
        completed = subprocess.run(
            ["ipconfig"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8.0,
        )
        output = completed.stdout if completed.returncode == 0 else ""
        if output:
            return _parse_ipconfig_adapters(output)
    except Exception:
        return []

    return []


def get_basic_network_info() -> str:
    """Return human-readable local network summary for PC diagnostics."""
    lines: List[str] = [f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", "Adapter network settings:"]
    adapters = get_network_adapters_info()
    if not adapters:
        lines.append("- No adapter details available.")
        return "\n".join(lines)

    for adapter in adapters:
        lines.append(f"- Adapter: {adapter.adapter_name}")
        lines.append(f"  Network: {adapter.network_name}")
        lines.append(f"  MAC: {adapter.mac_address}")
        if adapter.ipv4_with_masks:
            for item in adapter.ipv4_with_masks:
                lines.append(f"  IPv4/Subnet: {item}")
        else:
            lines.append("  IPv4/Subnet: - / -")
    return "\n".join(lines)
