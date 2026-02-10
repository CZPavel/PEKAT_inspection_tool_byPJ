from __future__ import annotations

import socket
from typing import Optional


class TCPController:
    def __init__(self, host: str, port: int, timeout_sec: float = 3.0) -> None:
        self.host = host
        self.port = port
        self.timeout_sec = timeout_sec
        self._request_id = 0

    def _next_request_id(self) -> str:
        self._request_id += 1
        return str(self._request_id)

    @staticmethod
    def _strip_request_id(response: str) -> str:
        if not response:
            return response
        if "." in response:
            prefix, rest = response.split(".", 1)
            if prefix.isdigit():
                return rest
        if ":" in response:
            prefix, rest = response.split(":", 1)
            if prefix.isdigit():
                return rest
        return response

    @staticmethod
    def _is_invalid(response: str) -> bool:
        lower = response.lower()
        return "invalid-command" in lower or "unknown command" in lower

    def send(self, command: str, project_path: str) -> str:
        base = f"{command}:{project_path}"
        request_id = self._next_request_id()
        candidates = [base, f"{request_id}.{base}"]
        payloads = []
        for candidate in candidates:
            payloads.extend(
                [
                    candidate,
                    f"{candidate}\n",
                    f"{candidate}\r\n",
                ]
            )
        last_response = ""
        for payload in payloads:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_sec) as sock:
                sock.sendall(payload.encode("utf-8"))
                sock.settimeout(self.timeout_sec)
                response = sock.recv(64)
            raw_response = response.decode("utf-8", errors="ignore").strip()
            cleaned = self._strip_request_id(raw_response)
            last_response = cleaned
            if not raw_response or self._is_invalid(raw_response):
                continue
            return cleaned
        return last_response

    def start(self, project_path: str) -> str:
        return self.send("start", project_path)

    def stop(self, project_path: str) -> str:
        return self.send("stop", project_path)

    def status(self, project_path: str) -> str:
        return self.send("status", project_path)

    def switch(self, project_path: str) -> str:
        return self.send("switch", project_path)
