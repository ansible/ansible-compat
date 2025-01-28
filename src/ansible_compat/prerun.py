"""Utilities for configuring ansible runtime environment."""

import hashlib
import os
import tempfile
from pathlib import Path


def get_cache_dir(project_dir: Path, *, isolated: bool = True) -> Path:
    """Compute cache directory to be used based on project path.

    Args:
        project_dir: Path to the project directory.
        isolated: Whether to use isolated cache directory.

    Returns:
        Cache directory path.

    Raises:
        RuntimeError: if cache directory is not writable.
    """
    cache_dir = Path(os.environ.get("ANSIBLE_HOME", "~/.ansible")).expanduser()

    if "VIRTUAL_ENV" in os.environ:
        path = Path(os.environ["VIRTUAL_ENV"])
        if not path.exists():  # pragma: no cover
            msg = f"VIRTUAL_ENV={os.environ['VIRTUAL_ENV']} does not exist."
            raise RuntimeError(msg)
        cache_dir = path.resolve() / ".ansible"
    elif isolated:
        if not project_dir.exists() or not os.access(project_dir, os.W_OK):
            # As "project_dir" can also be "/" and user might not be able
            # to write to it, we use a temporary directory as fallback.
            checksum = hashlib.sha256(
                project_dir.as_posix().encode("utf-8"),
            ).hexdigest()[:4]

            cache_dir = Path(tempfile.gettempdir()) / f".ansible-{checksum}"
            cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            cache_dir = project_dir.resolve() / ".ansible"

    # Ensure basic folder structure exists so `ansible-galaxy list` does not
    # fail with: None of the provided paths were usable. Please specify a valid path with
    try:
        for name in ("roles", "collections"):
            (cache_dir / name).mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover
        msg = "Failed to create cache directory."
        raise RuntimeError(msg) from exc

    return cache_dir
