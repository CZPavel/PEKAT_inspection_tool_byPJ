from __future__ import annotations

import time
from typing import Any, Optional

from ..clients.projects_http import ProjectsManagerHttp
from ..clients.rest_client import RestClient
from ..clients.sdk_client import SDKClient
from ..clients.tcp_controller import TCPController
from ..config import AppConfig


class ConnectionManager:
    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.client: Optional[object] = None
        self.state: str = "disconnected"
        self.status_text: str = "disconnected"
        self.last_context: Optional[dict[str, Any]] = None
        self.last_data: str = ""
        self.last_production_mode: Optional[bool] = None
        self.total_sent: int = 0
        self.sent_list: list[str] = []
        self._lock = None
        self._restart_in_progress = False

        try:
            import threading

            self._lock = threading.Lock()
        except Exception:
            self._lock = None

    def is_connected(self) -> bool:
        return self.state == "connected"

    def update_config(self, config: AppConfig) -> None:
        self.config = config

    def update_last_context(self, context: Optional[dict[str, Any]]) -> None:
        self.last_context = context
        if isinstance(context, dict) and "Production_Mode" in context:
            self.last_production_mode = bool(context.get("Production_Mode"))
        else:
            self.last_production_mode = None

    def update_last_data(self, data_value: str) -> None:
        self.last_data = data_value

    def record_sent(self, path: str) -> None:
        if self._lock:
            with self._lock:
                self.total_sent += 1
                self.sent_list.append(path)
                if len(self.sent_list) > 10000:
                    self.sent_list.pop(0)
        else:
            self.total_sent += 1
            self.sent_list.append(path)

    def reset_counters(self) -> None:
        if self._lock:
            with self._lock:
                self.total_sent = 0
                self.sent_list = []
        else:
            self.total_sent = 0
            self.sent_list = []

    def connect(self) -> bool:
        if self.state in {"connected", "connecting"}:
            return True
        self.state = "connecting"
        self.status_text = "connecting"

        if self._should_auto_start():
            self._pm_start()

        self.client = self._create_client()
        if self._ping_client():
            self.state = "connected"
            self.status_text = "connected"
            return True

        if self._should_auto_restart():
            return self._auto_restart_sequence()

        self.state = "error"
        self.status_text = "connection error"
        return False

    def disconnect(self) -> None:
        if self.state == "disconnected":
            return
        self.state = "disconnecting"
        self.status_text = "disconnecting"

        if self._should_auto_stop():
            self._pm_stop()

        if self.client is not None:
            try:
                self.client.stop()
            except Exception:
                pass
        self.client = None
        self.state = "disconnected"
        self.status_text = "disconnected"

    def check_health(self) -> bool:
        if self.client is None:
            self.state = "disconnected"
            self.status_text = "disconnected"
            return False
        ok = self._ping_client()
        if ok:
            self.state = "connected"
            self.status_text = "connected"
            return True
        self.state = "reconnecting"
        self.status_text = "reconnecting"
        if self._should_auto_restart():
            return self._auto_restart_sequence()
        return False

    def _create_client(self):
        if self.config.mode == "rest":
            return RestClient(
                host=self.config.host,
                port=self.config.port,
                api_key=self.config.rest.api_key,
                api_key_location=self.config.rest.api_key_location,
                api_key_name=self.config.rest.api_key_name,
                use_session=self.config.rest.use_session,
            )
        return SDKClient(
            host=self.config.host,
            port=self.config.port,
            project_path=self.config.project_path,
            start_mode=self.config.start_mode,
            already_running=self.config.already_running,
        )

    def _ping_client(self) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def _pm_enabled(self) -> bool:
        pm = self.config.projects_manager
        return bool(pm.tcp_enabled and self.config.project_path)

    def _should_auto_start(self) -> bool:
        return self._pm_enabled() and self.config.connection.policy in {
            "auto_start",
            "auto_start_stop",
        }

    def _should_auto_stop(self) -> bool:
        return self._pm_enabled() and self.config.connection.policy == "auto_start_stop"

    def _should_auto_restart(self) -> bool:
        return self._pm_enabled() and self.config.connection.policy == "auto_restart"

    def _pm_start(self) -> None:
        if not self._pm_enabled():
            self.logger.warning("PM TCP not enabled or project_path missing.")
            return
        try:
            controller = TCPController(
                host=self.config.projects_manager.tcp_host,
                port=self.config.projects_manager.tcp_port,
            )
            response = controller.start(self.config.project_path)
            if response == "timeout":
                self.logger.info("PM start pending (no response). Waiting for status.")
            else:
                self.logger.info("PM start response: %s", response)
            self._wait_pm_status(controller, target="running", timeout=30)
        except Exception as exc:
            self.logger.warning("PM start failed: %s", exc)

    def _pm_stop(self) -> None:
        if not self._pm_enabled():
            return
        try:
            controller = TCPController(
                host=self.config.projects_manager.tcp_host,
                port=self.config.projects_manager.tcp_port,
            )
            response = controller.stop(self.config.project_path)
            if response == "timeout":
                self.logger.info("PM stop pending (no response). Waiting for status.")
            else:
                self.logger.info("PM stop response: %s", response)
            self._wait_pm_status(controller, target="stopped", timeout=30)
        except Exception as exc:
            self.logger.warning("PM stop failed: %s", exc)

    def _wait_pm_status(self, controller: TCPController, target: str, timeout: int) -> None:
        start = time.time()
        while time.time() - start < timeout:
            status = controller.status(self.config.project_path)
            if status == target:
                return
            time.sleep(1)

    def _auto_restart_sequence(self) -> bool:
        if self._restart_in_progress:
            return False
        self._restart_in_progress = True
        attempts = self.config.connection.reconnect_attempts
        delay = self.config.connection.reconnect_delay_sec
        for attempt in range(1, attempts + 1):
            self.state = "reconnecting"
            self.status_text = f"trying to reconnect ({attempt}/{attempts})"
            self.logger.warning("Auto-restart attempt %s/%s", attempt, attempts)
            self._pm_stop()
            time.sleep(2)
            self._pm_start()
            for remaining in range(delay, 0, -1):
                self.status_text = (
                    f"trying to reconnect ({attempt}/{attempts}) in {remaining}s"
                )
                time.sleep(1)
            self.client = self._create_client()
            if self._ping_client():
                self.state = "connected"
                self.status_text = "connected"
                self._restart_in_progress = False
                return True
        self.state = "error"
        self.status_text = f"fail to reconnect after {attempts}x try"
        self._restart_in_progress = False
        return False

    def list_projects(self) -> list[dict[str, Any]]:
        if not self.config.projects_manager.enable_http_list:
            return []
        client = ProjectsManagerHttp(self.config.projects_manager.http_base_url)
        return client.list_projects()
