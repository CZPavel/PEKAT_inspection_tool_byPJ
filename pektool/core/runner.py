from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import AppConfig
from .connection import ConnectionManager
from .artifact_saver import save_artifacts
from .context_eval import normalize_context_evaluation
from .file_actions import apply_file_action
from ..io.file_scanner import FileScanner
from ..types import AnalyzeResult, ArtifactSaveResult, FileActionResult, ImageTask, NormalizedEvaluation


class Runner:
    """File producer + analyze worker pipeline."""

    def __init__(self, config: AppConfig, connection: ConnectionManager, logger) -> None:
        self.config = config
        self.connection = connection
        self.logger = logger
        self.queue: "queue.Queue[ImageTask]" = queue.Queue(maxsize=config.behavior.queue_maxsize)
        self.stop_event = threading.Event()
        self.scanner_thread: Optional[threading.Thread] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.status = "stopped"
        self._jsonl_path = Path(config.logging.directory) / config.logging.jsonl_filename
        Path(config.logging.directory).mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self.scanner_thread and self.scanner_thread.is_alive():
            return
        if self.config.behavior.run_mode == "loop" and self.config.file_actions.enabled:
            self.logger.warning(
                "File manipulation is disabled in loop mode because it would be non-deterministic."
            )
            self.config.file_actions.enabled = False
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
        return self.connection.total_sent

    def _scanner_loop(self) -> None:
        # Producer side: build tasks according to selected run mode.
        input_cfg = self.config.input
        behavior = self.config.behavior

        if input_cfg.source_type == "files":
            files = [Path(p) for p in input_cfg.files]
            if behavior.run_mode == "just_watch":
                # "Just watch" has no meaning for fixed file list mode.
                self.logger.warning("Run mode 'just_watch' is not compatible with source_type=files; using once.")
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
            # Freeze current stable file set and keep replaying it.
            snapshot = self._build_snapshot(scanner)
            while not self.stop_event.is_set():
                self._enqueue_files(snapshot, loop=False)
                time.sleep(self.config.input.poll_interval_sec)
        elif behavior.run_mode == "once":
            # Process existing stable files only once.
            self._run_once(scanner)
            self._finalize_once()
        elif behavior.run_mode == "just_watch":
            # Ignore files present at startup and process only newly appearing ones.
            self._run_just_watch(scanner, folder)
        else:
            # Process current files once, then keep watching for new files.
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

    def _run_just_watch(self, scanner: FileScanner, folder: Path) -> None:
        seen: Set[Path] = self._collect_existing_paths(folder)
        while not self.stop_event.is_set():
            ready = scanner.scan()
            new_files = [path for path in ready if path not in seen]
            if new_files:
                seen.update(new_files)
                self._enqueue_files(new_files, loop=False)
            scanner.wait(self.config.input.poll_interval_sec)

    def _collect_existing_paths(self, folder: Path) -> Set[Path]:
        # Collect startup snapshot so "just_watch" ignores pre-existing files.
        include_subfolders = self.config.input.include_subfolders
        extensions = {ext.lower() for ext in self.config.input.extensions}
        if not folder.exists():
            return set()
        iterator = folder.rglob("*") if include_subfolders else folder.glob("*")
        paths: Set[Path] = set()
        for path in iterator:
            if path.is_file() and path.suffix.lower() in extensions:
                paths.add(path)
        return paths

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
        # Consumer side: process queued tasks sequentially to avoid PEKAT overload.
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
            context, image_bytes = self._analyze_with_retry(task)
            self.connection.update_last_context(context)
            latency_ms = int((time.perf_counter() - start) * 1000)
            self.connection.record_sent(str(task.path))
            fallback_ok_nok = self._extract_ok_nok(context)
            evaluation = normalize_context_evaluation(
                context=context,
                fallback_ok_nok=fallback_ok_nok,
                latency_ms=latency_ms,
                oknok_source=self.config.pekat.oknok_source,
            )
            self.connection.record_evaluation(
                complete_time_ms=evaluation.complete_time_ms,
                ok_nok=evaluation.ok_nok,
                context=context,
                error=None,
            )
            file_action_result = self._apply_file_action(task.path, evaluation)
            artifact_save_result = self._save_artifacts(
                path=task.path,
                context=context,
                image_bytes=image_bytes,
                evaluation=evaluation,
            )
            return AnalyzeResult(
                status="ok",
                latency_ms=latency_ms,
                error=None,
                context=context,
                ok_nok=evaluation.ok_nok,
                evaluation=evaluation,
                file_action=file_action_result,
                image_bytes=image_bytes,
                artifact_save=artifact_save_result,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            if self._should_requeue(exc):
                self.logger.warning("Transient error, requeueing %s: %s", task.path, exc)
                self._requeue_task(task)
                return None
            self.connection.record_evaluation(
                complete_time_ms=None,
                ok_nok=None,
                context=None,
                error=str(exc),
            )
            return AnalyzeResult(
                status="error",
                latency_ms=latency_ms,
                error=str(exc),
                context=None,
                ok_nok=None,
                file_action=None,
                image_bytes=None,
                artifact_save=None,
            )

    def _apply_file_action(
        self,
        path: Path,
        evaluation: NormalizedEvaluation,
    ) -> FileActionResult:
        try:
            result = apply_file_action(path=path, evaluation=evaluation, cfg=self.config, now=datetime.now())
        except Exception as exc:  # pragma: no cover - safety net around plugin-like call
            self.logger.warning("File action failed unexpectedly for %s: %s", path, exc)
            return FileActionResult(
                applied=False,
                operation="none",
                source_path=str(path),
                target_path=None,
                reason=f"runner-file-action-exception:{exc}",
                eval_status=evaluation.eval_status,
            )

        if self.config.file_actions.enabled:
            if result.applied:
                if result.operation == "move":
                    self.logger.info("File moved: %s -> %s", result.source_path, result.target_path)
                elif result.operation == "delete":
                    self.logger.info("File deleted: %s", result.source_path)
            elif result.reason and result.reason != "file-actions-disabled":
                self.logger.warning(
                    "File action not applied for %s: %s",
                    result.source_path,
                    result.reason,
                )
        return result

    def _save_artifacts(
        self,
        path: Path,
        context: Optional[Dict[str, Any]],
        image_bytes: Optional[bytes],
        evaluation: NormalizedEvaluation,
    ) -> ArtifactSaveResult:
        try:
            result = save_artifacts(
                source_path=path,
                context=context,
                image_bytes=image_bytes,
                evaluation=evaluation,
                cfg=self.config,
                now=datetime.now(),
            )
        except Exception as exc:  # pragma: no cover - defensive path
            self.logger.warning("Artifact save failed unexpectedly for %s: %s", path, exc)
            return ArtifactSaveResult(
                json_saved=False,
                json_path=None,
                processed_saved=False,
                processed_path=None,
                reason=f"artifact-save-exception:{exc}",
            )

        if self.config.file_actions.save_json_context or self.config.file_actions.save_processed_image:
            if result.reason:
                self.logger.warning("Artifact save warning for %s: %s", path, result.reason)
            else:
                if result.json_saved:
                    self.logger.info("JSON context saved: %s", result.json_path)
                if result.processed_saved:
                    self.logger.info("Processed image saved: %s", result.processed_path)
        return result

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
        evaluation = result.evaluation or NormalizedEvaluation(
            eval_status="ERROR",
            result_bool=None,
            ok_nok=result.ok_nok,
            complete_time_s=None,
            complete_time_ms=None,
            detected_count=0,
        )
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "filename": str(task.path),
            "data": task.data_value,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "ok_nok": result.ok_nok,
            "eval_status": evaluation.eval_status,
            "result_bool": evaluation.result_bool,
            "complete_time_s": evaluation.complete_time_s,
            "complete_time_ms": evaluation.complete_time_ms,
            "detected_count": evaluation.detected_count,
            "file_action_applied": result.file_action.applied if result.file_action else False,
            "file_action_operation": result.file_action.operation if result.file_action else "none",
            "file_action_target": result.file_action.target_path if result.file_action else None,
            "file_action_reason": result.file_action.reason if result.file_action else None,
            "json_context_saved": result.artifact_save.json_saved if result.artifact_save else False,
            "json_context_path": result.artifact_save.json_path if result.artifact_save else None,
            "processed_image_saved": result.artifact_save.processed_saved if result.artifact_save else False,
            "processed_image_path": result.artifact_save.processed_path if result.artifact_save else None,
            "artifact_reason": result.artifact_save.reason if result.artifact_save else None,
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
            response_type = cfg.response_type
            if self.config.file_actions.save_processed_image:
                response_type = self.config.file_actions.processed_response_type
            return client.analyze(
                task.path,
                data=task.data_value,
                timeout_sec=cfg.timeout_sec,
                response_type=response_type,
                context_in_body=cfg.context_in_body,
            )

        return _run()

