from __future__ import annotations

import socket
from typing import Optional


class TCPController:
    def __init__(self, host: str, port: int, timeout_sec: float = 3.0) -> None:
        self.host = host
        self.port = port
        self.timeout_sec = timeout_sec

    def send(self, command: str, project_path: str) -> str:
        payloads = [
            f"{command}:{project_path}",
            f"{command}:{project_path}\n",
            f"{command}:{project_path}\r\n",
        ]
        last_response = ""
        for payload in payloads:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_sec) as sock:
                sock.sendall(payload.encode("utf-8"))
                sock.settimeout(self.timeout_sec)
                response = sock.recv(64)
            last_response = response.decode("utf-8", errors="ignore").strip()
            if not last_response or "invalid-command" in last_response or "Unknown command" in last_response:
                continue
            return last_response
        return last_response

    def start(self, project_path: str) -> str:
        return self.send("start", project_path)

    def stop(self, project_path: str) -> str:
        return self.send("stop", project_path)

    def status(self, project_path: str) -> str:
        return self.send("status", project_path)

    def switch(self, project_path: str) -> str:
        return self.send("switch", project_path)
