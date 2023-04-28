"""Tests for ansible_compat.prerun module."""
from pathlib import Path

from ansible_compat.prerun import get_cache_dir


def test_get_cache_dir_relative() -> None:
    """Test behaviors of get_cache_dir."""
    relative_path = Path(".")
    abs_path = relative_path.resolve()
    assert get_cache_dir(relative_path) == get_cache_dir(abs_path)
