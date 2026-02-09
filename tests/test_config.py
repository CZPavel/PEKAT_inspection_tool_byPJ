from pathlib import Path

from pektool.config import load_config


def test_load_config_example():
    path = Path(__file__).resolve().parents[1] / "configs" / "config.example.yaml"
    cfg = load_config(path)
    assert cfg.host
    assert cfg.port