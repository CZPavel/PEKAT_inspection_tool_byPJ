import socketserver
import threading
from contextlib import contextmanager

from pektool.clients.tcp_controller import TCPController


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request.recv(1024).decode("utf-8", errors="ignore").strip()
        response = self.server.responder(data)  # type: ignore[attr-defined]
        if response is None:
            return
        self.request.sendall(response.encode("utf-8"))


@contextmanager
def _run_server(responder):
    server = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    server.responder = responder  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()


def test_pipe_format_status():
    def responder(data: str) -> str:
        if data.startswith("status|"):
            return "suc:running"
        return "err:invalid-command"

    with _run_server(responder) as (host, port):
        controller = TCPController(host=host, port=port, timeout_sec=1.0)
        assert controller.status("C:\\Path") == "running"


def test_fallback_colon_format():
    def responder(data: str) -> str:
        if "|" in data:
            return "err:invalid-command"
        if data.startswith("start:"):
            return "done"
        return "err:invalid-command"

    with _run_server(responder) as (host, port):
        controller = TCPController(host=host, port=port, timeout_sec=1.0)
        assert controller.start("C:\\Path") == "done"
