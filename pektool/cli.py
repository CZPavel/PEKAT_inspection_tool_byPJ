from __future__ import annotations

import signal
import time
from pathlib import Path
from typing import List, Optional

import typer

from .clients.projects_http import ProjectsManagerHttp
from .clients.tcp_controller import TCPController
from .config import AppConfig, load_config
from .core.connection import ConnectionManager
from .core.runner import Runner
from .logging_setup import setup_logging

app = typer.Typer(add_completion=False)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "config.example.yaml"


def _load_config(path: Optional[Path]) -> AppConfig:
    if path is None:
        return AppConfig()
    return load_config(path)


@app.command()
def run(
    config: Optional[Path] = typer.Option(None, "--config", help="Path to YAML config"),
    folder: Optional[Path] = typer.Option(None, "--folder", help="Input folder"),
    files: List[Path] = typer.Option(None, "--files", help="Specific files"),
    mode: Optional[str] = typer.Option(None, "--mode", help="sdk|rest"),
    host: Optional[str] = typer.Option(None, "--host"),
    port: Optional[int] = typer.Option(None, "--port"),
    include_subfolders: Optional[bool] = typer.Option(None, "--include-subfolders/--no-include-subfolders"),
    run_mode: Optional[str] = typer.Option(None, "--run-mode", help="loop|once|initial_then_watch"),
    data_prefix: Optional[str] = typer.Option(None, "--data-prefix", help="Legacy prefix"),
    data_string: Optional[str] = typer.Option(None, "--data-string"),
    data_include_filename: Optional[bool] = typer.Option(
        None, "--include-filename/--no-include-filename"
    ),
    data_include_timestamp: Optional[bool] = typer.Option(
        None, "--include-timestamp/--no-include-timestamp"
    ),
    data_include_string: Optional[bool] = typer.Option(
        None, "--include-string/--no-include-string"
    ),
    start_mode: Optional[str] = typer.Option(None, "--start-mode", help="auto|connect_only|always_start"),
) -> None:
    if config is None:
        config = _default_config_path() if _default_config_path().exists() else None

    cfg = _load_config(config)

    if mode:
        cfg.mode = mode
    if host:
        cfg.host = host
    if port:
        cfg.port = port
    if folder:
        cfg.input.source_type = "folder"
        cfg.input.folder = str(folder)
    if files:
        cfg.input.source_type = "files"
        cfg.input.files = [str(path) for path in files]
    if include_subfolders is not None:
        cfg.input.include_subfolders = include_subfolders
    if run_mode:
        cfg.behavior.run_mode = run_mode
    if data_prefix is not None:
        cfg.pekat.data_include_string = True
        cfg.pekat.data_string_value = data_prefix
    if data_string is not None:
        cfg.pekat.data_include_string = True
        cfg.pekat.data_string_value = data_string
    if data_include_filename is not None:
        cfg.pekat.data_include_filename = data_include_filename
    if data_include_timestamp is not None:
        cfg.pekat.data_include_timestamp = data_include_timestamp
    if data_include_string is not None:
        cfg.pekat.data_include_string = data_include_string
    if start_mode:
        cfg.start_mode = start_mode

    logger = setup_logging(cfg.logging)
    connection = ConnectionManager(cfg, logger)
    if not connection.connect():
        typer.echo("Failed to connect to PEKAT instance.")
        return
    runner = Runner(cfg, connection, logger)

    def _graceful_stop(*_args):
        runner.stop()
        connection.disconnect()

    signal.signal(signal.SIGINT, _graceful_stop)
    signal.signal(signal.SIGTERM, _graceful_stop)

    runner.start()
    logger.info("Runner started")
    try:
        while not runner.stop_event.is_set():
            time.sleep(1.0)
    except KeyboardInterrupt:
        _graceful_stop()


@app.command()
def ping(
    config: Optional[Path] = typer.Option(None, "--config"),
) -> None:
    if config is None:
        config = _default_config_path() if _default_config_path().exists() else None
    cfg = _load_config(config)
    connection = ConnectionManager(cfg, setup_logging(cfg.logging))
    ok = connection.connect()
    typer.echo("OK" if ok else "FAILED")


pm = typer.Typer()
app.add_typer(pm, name="pm")


@pm.command("status")
def pm_status(
    project_path: str = typer.Option(..., "--project"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(7002, "--port"),
) -> None:
    controller = TCPController(host=host, port=port)
    typer.echo(controller.status(project_path))


@pm.command("start")
def pm_start(
    project_path: str = typer.Option(..., "--project"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(7002, "--port"),
) -> None:
    controller = TCPController(host=host, port=port)
    typer.echo(controller.start(project_path))


@pm.command("stop")
def pm_stop(
    project_path: str = typer.Option(..., "--project"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(7002, "--port"),
) -> None:
    controller = TCPController(host=host, port=port)
    typer.echo(controller.stop(project_path))


@pm.command("switch")
def pm_switch(
    project_path: str = typer.Option(..., "--project"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(7002, "--port"),
) -> None:
    controller = TCPController(host=host, port=port)
    typer.echo(controller.switch(project_path))


@pm.command("list")
def pm_list(
    base_url: str = typer.Option("http://127.0.0.1:7000", "--base-url"),
) -> None:
    client = ProjectsManagerHttp(base_url=base_url)
    projects = client.list_projects()
    for item in projects:
        typer.echo(item)


if __name__ == "__main__":
    app()

