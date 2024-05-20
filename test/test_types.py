"""Tests for types module."""

import ansible_compat.types


def test_types() -> None:
    """Tests that JSON types are exported."""
    assert ansible_compat.types.JSON
    assert ansible_compat.types.JSON_ro
