"""Test compatibility functions."""

from __future__ import annotations

import pytest
from packaging.version import Version

from ansible_compat.compatibility import should_auto_enable_plugin_loader


@pytest.mark.parametrize(
    ("ansible_lint_version", "expected"),
    (
        # ansible-lint < 25.8.1 should auto-enable
        ("25.8.0", True),
        ("25.7.9", True),
        ("25.0.0", True),
        ("24.9.9", True),
        ("6.22.2", True),
        # ansible-lint >= 25.8.1 should not auto-enable
        ("25.8.1", False),
        ("25.8.2", False),
        ("25.9.0", False),
        ("26.0.0", False),
        ("30.0.0", False),
        # No ansible-lint should not auto-enable
        (None, False),
    ),
)
def test_should_auto_enable_plugin_loader(
    ansible_lint_version: str | None,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test should_auto_enable_plugin_loader with different ansible-lint versions.

    Args:
        ansible_lint_version: The ansible-lint version to mock, or None for no ansible-lint.
        expected: The expected result from should_auto_enable_plugin_loader().
        monkeypatch: Pytest fixture for mocking.
    """

    def mock_ansible_lint_version() -> Version | None:
        if ansible_lint_version is None:
            return None
        return Version(ansible_lint_version)

    monkeypatch.setattr(
        "ansible_compat.compatibility.ansible_lint_version",
        mock_ansible_lint_version,
    )

    result = should_auto_enable_plugin_loader()
    assert (
        result is expected
    ), f"Expected {expected} for ansible-lint {ansible_lint_version}, got {result}"
