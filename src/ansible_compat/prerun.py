"""Utilities for configuring ansible runtime environment."""

import os
import warnings
from functools import cache
from pathlib import Path


@cache
def get_cache_dir(project_dir: Path) -> Path:
    """Compute cache directory to be used based on project path."""
    venv_path = os.environ.get("VIRTUAL_ENV", None)
    if not venv_path:
        cache_dir = Path(project_dir) / ".cache"
        warnings.warn(
            f"No VIRTUAL_ENV found, will use of unisolated cache directory: {cache_dir}",
            stacklevel=0,
        )
    else:
        cache_dir = Path(venv_path) / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
