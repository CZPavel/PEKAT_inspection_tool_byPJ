from pektool.config import AppConfig
from pektool.core.connection import ConnectionManager


class _DummyLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


def test_production_mode_key_variants():
    manager = ConnectionManager(AppConfig(), _DummyLogger())

    manager.update_last_context({"Production_Mode": True})
    assert manager.last_production_mode is True

    manager.update_last_context({"productionMode": "off"})
    assert manager.last_production_mode is False

    manager.update_last_context({"production_mode": 1})
    assert manager.last_production_mode is True
