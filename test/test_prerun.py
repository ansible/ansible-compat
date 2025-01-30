"""Tests for ansible_compat.prerun module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

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
    with (
        pytest.warns(
            UserWarning,
            match=r"Project directory /.ansible cannot be used for caching as it is not writable.",
        ),
        pytest.warns(
            UserWarning,
            match=r"Using unique temporary directory .* for caching.",
        ),
    ):
        cache_dir = get_cache_dir(Path("/"), isolated=True)
    assert cache_dir.as_posix().startswith(tempfile.gettempdir())


def test_get_cache_dir_venv_ro_project_ro(monkeypatch: MonkeyPatch) -> None:
    """Test behaviors of get_cache_dir with read-only virtual environment and read only project directory.

    Args:
        monkeypatch: Pytest fixture for monkeypatching
    """
    monkeypatch.setenv("VIRTUAL_ENV", "/")
    monkeypatch.delenv("ANSIBLE_HOME", raising=False)
    with (
        pytest.warns(
            UserWarning,
            match=r"Using unique temporary directory .* for caching.",
        ),
        pytest.warns(
            UserWarning,
            match=r"Found VIRTUAL_ENV=/ but we cannot use it for caching as it is not writable.",
        ),
        pytest.warns(
            UserWarning,
            match=r"Project directory .* cannot be used for caching as it is not writable.",
        ),
    ):
        cache_dir = get_cache_dir(Path("/etc"), isolated=True)
    assert cache_dir.as_posix().startswith(tempfile.gettempdir())
