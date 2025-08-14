"""Compatibility functions for ansible_compat.

This module contains functions that handle backward compatibility
with different versions of ansible-lint and other tools.
"""

from __future__ import annotations

from packaging.version import Version

from ansible_compat.constants import ANSIBLE_LINT_MIN_VERSION_EARLY_LOADER
from ansible_compat.utils import ansible_lint_version


def should_auto_enable_plugin_loader() -> bool:
    """Check if plugin loader should be auto-enabled for backwards compatibility.

    Returns True if ansible-lint version is < ANSIBLE_LINT_MIN_VERSION_EARLY_LOADER.

    Returns:
        True if plugin loader should be auto-enabled, False otherwise.
    """
    # Check ansible-lint version
    lint_version = ansible_lint_version()
    return lint_version is not None and lint_version < Version(
        ANSIBLE_LINT_MIN_VERSION_EARLY_LOADER,
    )
