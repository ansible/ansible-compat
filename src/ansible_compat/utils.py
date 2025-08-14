"""Utility functions for ansible_compat."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from packaging.version import Version

from ansible_compat.ports import cache


@cache
def ansible_lint_version() -> Version | None:
    """Return current Version object for ansible-lint if available.

    Returns:
        Version object for ansible-lint or None if not found.
    """
    try:
        return Version(version("ansible-lint"))
    except (ImportError, PackageNotFoundError):
        return None
