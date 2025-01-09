"""Utilities for configuring ansible runtime environment."""

import os
from pathlib import Path


def get_cache_dir(project_dir: Path, *, isolated: bool = True) -> Path:
    """Compute cache directory to be used based on project path.

    Args:
        project_dir: Path to the project directory.
        isolated: Whether to use isolated cache directory.

    Returns:
        Cache directory path.
    """
    if "VIRTUAL_ENV" in os.environ:
        cache_dir = Path(os.environ["VIRTUAL_ENV"]) / ".ansible"
    elif isolated:
        cache_dir = project_dir / ".ansible"
    else:
        cache_dir = Path(os.environ.get("ANSIBLE_HOME", "~/.ansible")).expanduser()

    # Ensure basic folder structure exists so `ansible-galaxy list` does not
    # fail with: None of the provided paths were usable. Please specify a valid path with
    for name in ("roles", "collections"):  # pragma: no cover
        (cache_dir / name).mkdir(parents=True, exist_ok=True)

    return cache_dir
