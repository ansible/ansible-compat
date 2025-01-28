"""Tests for ansible_compat.prerun module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

from ansible_compat.prerun import get_cache_dir


def test_get_cache_dir_relative() -> None:
    """Test behaviors of get_cache_dir."""
    relative_path = Path()
    abs_path = relative_path.resolve()
    assert get_cache_dir(relative_path) == get_cache_dir(abs_path)


def test_get_cache_dir_no_isolation_no_venv(monkeypatch: MonkeyPatch) -> None:
    """Test behaviors of get_cache_dir.

    Args:
        monkeypatch: Pytest fixture for monkeypatching
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("ANSIBLE_HOME", raising=False)
    assert get_cache_dir(Path(), isolated=False) == Path("~/.ansible").expanduser()


def test_get_cache_dir_isolation_no_venv(monkeypatch: MonkeyPatch) -> None:
    """Test behaviors of get_cache_dir.

    Args:
        monkeypatch: Pytest fixture for monkeypatching
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("ANSIBLE_HOME", raising=False)
    cache_dir = get_cache_dir(Path(), isolated=True)
    assert cache_dir == Path().cwd() / ".ansible"


def test_get_cache_dir_isolation_no_venv_root(monkeypatch: MonkeyPatch) -> None:
    """Test behaviors of get_cache_dir.

    Args:
        monkeypatch: Pytest fixture for monkeypatching
    """
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("ANSIBLE_HOME", raising=False)
    cache_dir = get_cache_dir(Path("/"), isolated=True)
    assert cache_dir.as_posix().startswith(tempfile.gettempdir())
