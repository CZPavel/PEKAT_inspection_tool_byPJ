from __future__ import annotations

import signal
import time
from pathlib import Path
from typing import List, Optional

import typer

from .clients.projects_http import ProjectsManagerHttp
from .clients.rest_client import RestClient
from .clients.sdk_client import SDKClient
from .clients.tcp_controller import TCPController
from .config import AppConfig, load_config
from .core.runner import Runner
from .logging_setup import setup_logging

app = typer.Typer(add_completion=False)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "configs" / "config.example.yaml"


def _load_config(path: Optional[Path]) -> AppConfig:
    if path is None:
        return AppConfig()
    return load_config(path)


def _create_client(config: AppConfig):
    if config.mode == "rest":
        return RestClient(
            host=config.host,
            port=config.port,
            api_key=config.rest.api_key,
            api_key_location=config.rest.api_key_location,
            api_key_name=config.rest.api_key_name,
            use_session=config.rest.use_session,
        )
    return SDKClient(
        host=config.host,
        port=config.port,
        project_path=config.project_path,
        start_mode=config.start_mode,
        already_running=config.already_running,
    )


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
    data_prefix: Optional[str] = typer.Option(None, "--data-prefix"),
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
        cfg.pekat.data_prefix = data_prefix
    if start_mode:
        cfg.start_mode = start_mode

    logger = setup_logging(cfg.logging)
    client = _create_client(cfg)
    runner = Runner(cfg, client, logger)

    def _graceful_stop(*_args):
        runner.stop()
        client.stop()

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
    client = _create_client(cfg)
    ok = client.ping()
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
