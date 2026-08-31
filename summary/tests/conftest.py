"""
Conftest для pytest.

Отключает pytest logging plugin, чтобы не конфликтовал с JSON-форматтером.
Гарантирует тестовую среду ENV=test.
"""

import os

import pytest


def pytest_configure(config):
    """Отключаем pytest logging plugin при загрузке pytest."""
    # Отключаем log_cli — он конфликтует с нашим JSON-форматтером
    config.option.log_cli = False


@pytest.fixture(autouse=True)
def _setup_env():
    """Устанавливает тестовую среду перед каждым тестом."""
    os.environ.setdefault("ENV", "test")
    yield
