"""Tests for ansible_compat.prerun module."""
import os

from ansible_compat.prerun import get_cache_dir


def test_get_cache_dir_relative() -> None:
    """Test behaviors of get_cache_dir."""
    relative_path = "."
    abs_path = os.path.abspath(relative_path)
    assert get_cache_dir(relative_path) == get_cache_dir(abs_path)
