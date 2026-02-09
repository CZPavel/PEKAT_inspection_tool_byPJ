from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import AppConfig
from .connection import ConnectionManager
from ..io.file_scanner import FileScanner
from ..types import AnalyzeResult, ImageTask


class Runner:
    def __init__(self, config: AppConfig, connection: ConnectionManager, logger) -> None:
        self.config = config
        self.connection = connection
        self.logger = logger
        self.queue: "queue.Queue[ImageTask]" = queue.Queue(maxsize=config.behavior.queue_maxsize)
        self.stop_event = threading.Event()
        self.scanner_thread: Optional[threading.Thread] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.sent_count = 0
        self.status = "stopped"
        self._jsonl_path = Path(config.logging.directory) / config.logging.jsonl_filename
        Path(config.logging.directory).mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self.scanner_thread and self.scanner_thread.is_alive():
            return
        self.stop_event.clear()
        self.status = "starting"
        self.scanner_thread = threading.Thread(target=self._scanner_loop, daemon=True)
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.scanner_thread.start()
        self.worker_thread.start()
        self.status = "running"

    def stop(self) -> None:
        self.stop_event.set()
        timeout = self.config.behavior.graceful_stop_timeout_sec
        for thread in [self.scanner_thread, self.worker_thread]:
            if thread:
                thread.join(timeout=timeout)
        self.status = "stopped"

    def get_status(self) -> str:
        return self.status

    def get_count(self) -> int:
        return self.sent_count

    def _scanner_loop(self) -> None:
        input_cfg = self.config.input
        behavior = self.config.behavior

        if input_cfg.source_type == "files":
            files = [Path(p) for p in input_cfg.files]
            self._enqueue_files(files, loop=behavior.run_mode == "loop")
            if behavior.run_mode != "loop":
                self._finalize_once()
            return

        folder = Path(input_cfg.folder)
        scanner = FileScanner(
            folder=folder,
            include_subfolders=input_cfg.include_subfolders,
            extensions=input_cfg.extensions,
            stability_checks=input_cfg.stability_checks,
            logger=self.logger,
        )

        if behavior.run_mode == "loop":
            snapshot = self._build_snapshot(scanner)
            while not self.stop_event.is_set():
                self._enqueue_files(snapshot, loop=False)
                time.sleep(self.config.input.poll_interval_sec)
        elif behavior.run_mode == "once":
            self._run_once(scanner)
            self._finalize_once()
        else:
            self._run_initial_then_watch(scanner)

    def _build_snapshot(self, scanner: FileScanner) -> List[Path]:
        idle_cycles = 0
        seen: Set[Path] = set()
        snapshot: List[Path] = []
        while not self.stop_event.is_set():
            ready = scanner.scan()
            new_files = [path for path in ready if path not in seen]
            if new_files:
                seen.update(new_files)
                snapshot.extend(new_files)
                idle_cycles = 0
            else:
                idle_cycles += 1
            if idle_cycles >= 2:
                break
            scanner.wait(self.config.input.poll_interval_sec)
        return snapshot

    def _run_once(self, scanner: FileScanner) -> None:
        idle_cycles = 0
        seen: Set[Path] = set()
        while not self.stop_event.is_set():
            ready = scanner.scan()
            new_files = [path for path in ready if path not in seen]
            if new_files:
                seen.update(new_files)
                self._enqueue_files(new_files, loop=False)
                idle_cycles = 0
            else:
                idle_cycles += 1
            if idle_cycles >= 2:
                break
            scanner.wait(self.config.input.poll_interval_sec)

    def _run_initial_then_watch(self, scanner: FileScanner) -> None:
        idle_cycles = 0
        seen: Set[Path] = set()
        while not self.stop_event.is_set() and idle_cycles < 2:
            ready = scanner.scan()
            new_files = [path for path in ready if path not in seen]
            if new_files:
                seen.update(new_files)
                self._enqueue_files(new_files, loop=False)
                idle_cycles = 0
            else:
                idle_cycles += 1
            scanner.wait(self.config.input.poll_interval_sec)

        while not self.stop_event.is_set():
            ready = scanner.scan()
            new_files = [path for path in ready if path not in seen]
            if new_files:
                seen.update(new_files)
                self._enqueue_files(new_files, loop=False)
            scanner.wait(self.config.input.poll_interval_sec)

    def _enqueue_files(self, files: List[Path], loop: bool) -> None:
        if not files:
            if loop:
                time.sleep(self.config.input.poll_interval_sec)
            return
        while not self.stop_event.is_set():
            for path in files:
                if self.stop_event.is_set():
                    return
                if not path.exists():
                    self.logger.warning("File missing: %s", path)
                    continue
                data_value = self._build_data_value(path)
                task = ImageTask(path=path, data_value=data_value)
                while not self.stop_event.is_set():
                    try:
                        self.queue.put(task, timeout=0.5)
                        break
                    except queue.Full:
                        continue
            if not loop:
                break
            time.sleep(self.config.input.poll_interval_sec)

    def _finalize_once(self) -> None:
        if not self.stop_event.is_set():
            self.queue.join()
            self.stop_event.set()

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            if not self.connection.is_connected():
                time.sleep(1.0)
                continue
            try:
                task = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            result = self._process_task(task)
            if result is not None:
                self._log_result(task, result)
            self.queue.task_done()
            delay = self.config.behavior.delay_between_images_ms
            if delay > 0:
                time.sleep(delay / 1000.0)

    def _process_task(self, task: ImageTask) -> Optional[AnalyzeResult]:
        start = time.perf_counter()
        try:
            self.connection.update_last_data(task.data_value)
            self.logger.info("Sending data: %s", task.data_value)
            context, _ = self._analyze_with_retry(task)
            self.connection.update_last_context(context)
            ok_nok = self._extract_ok_nok(context)
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.sent_count += 1
            return AnalyzeResult(status="ok", latency_ms=latency_ms, error=None, context=context, ok_nok=ok_nok)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            if self._should_requeue(exc):
                self.logger.warning("Transient error, requeueing %s: %s", task.path, exc)
                self._requeue_task(task)
                return None
            return AnalyzeResult(status="error", latency_ms=latency_ms, error=str(exc), context=None, ok_nok=None)

    def _extract_ok_nok(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        field = self.config.pekat.result_field
        if not field or not context:
            return None
        parts = field.split(".")
        value: Any = context
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        if isinstance(value, bool):
            return "OK" if value else "NOK"
        if isinstance(value, str):
            return value
        return None

    def _build_data_value(self, path: Path) -> str:
        parts: List[str] = []
        cfg = self.config.pekat
        if cfg.data_include_string and cfg.data_string_value:
            parts.append(cfg.data_string_value)
        if cfg.data_include_filename:
            parts.append(path.stem)
        if cfg.data_include_timestamp:
            parts.append(time.strftime("_%H_%M_%S_"))
        return "".join(parts)

    def _log_result(self, task: ImageTask, result: AnalyzeResult) -> None:
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "filename": str(task.path),
            "data": task.data_value,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "ok_nok": result.ok_nok,
            "error": result.error,
            "mode": self.config.mode,
        }
        with self._jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        if result.status == "error":
            self.logger.error("Analyze failed for %s: %s", task.path, result.error)
        else:
            self.logger.info("Processed %s (%s ms)", task.path, result.latency_ms)

    def _requeue_task(self, task: ImageTask) -> None:
        while not self.stop_event.is_set():
            try:
                self.queue.put(task, timeout=0.5)
                return
            except queue.Full:
                continue

    def _should_requeue(self, exc: Exception) -> bool:
        try:
            import requests  # type: ignore
            if isinstance(exc, requests.HTTPError):
                status = exc.response.status_code if exc.response is not None else 0
                return status >= 500 or status == 0
            request_errors = (requests.RequestException,)
        except Exception:
            request_errors = tuple()
        transient = (ConnectionError, TimeoutError, OSError) + request_errors
        return isinstance(exc, transient)

    def _analyze_with_retry(self, task: ImageTask):
        cfg = self.config.pekat

        @retry(
            stop=stop_after_attempt(cfg.retry.attempts),
            wait=wait_exponential(multiplier=cfg.retry.backoff_sec, max=cfg.retry.max_backoff_sec),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def _run():
            client = self.connection.client
            if client is None:
                raise RuntimeError("Not connected to PEKAT instance.")
            return client.analyze(
                task.path,
                data=task.data_value,
                timeout_sec=cfg.timeout_sec,
                response_type=cfg.response_type,
                context_in_body=cfg.context_in_body,
            )

        return _run()

