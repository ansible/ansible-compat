"""Utilities for configuring ansible runtime environment.

No import of ansible-core must happen within this file!
"""

import hashlib
import os
import sys
import tempfile
import warnings
from importlib.metadata import version
from pathlib import Path

from packaging.version import Version

# This module is early loaded by tools like ansible-lint and we want to fail
# fast even for `ansible-lint --version` if the setup is known as broken.
if sys.version_info >= (3, 14):
    core_version = Version(version("ansible-core"))
    if core_version < Version("2.20.0dev0"):  # pragma: no cover
        msg = f"Python 3.14 requires ansible-core version >= 2.20.0, and we found {core_version}."
        raise RuntimeError(msg)


def is_writable(path: Path) -> bool:
    """Check if path is writable, creating if necessary.

    Args:
        path: Path to check.

    Returns:
        True if path is writable, False otherwise.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return path.exists() and os.access(path, os.W_OK)


def get_cache_dir(project_dir: Path, *, isolated: bool = True) -> Path:
    """Compute cache directory to be used based on project path.

    Args:
        project_dir: Path to the project directory.
        isolated: Whether to use isolated cache directory.

    Returns:
        A writable cache directory.

    Raises:
        RuntimeError: if cache directory is not writable.
        OSError: if cache directory cannot be created.
    """
    cache_dir: Path | None = None
    if "VIRTUAL_ENV" in os.environ:
        path = Path(os.environ["VIRTUAL_ENV"]).resolve() / ".ansible"
        if is_writable(path):
            cache_dir = path
        else:
            msg = f"Found VIRTUAL_ENV={os.environ['VIRTUAL_ENV']} but we cannot use it for caching as it is not writable."  # pylint: disable=W0621
            warnings.warn(
                message=msg,
                stacklevel=2,
                source={"msg": msg},
            )

    if isolated:
        project_dir = project_dir.resolve() / ".ansible"
        if is_writable(project_dir):
            cache_dir = project_dir
        else:
            msg = f"Project directory {project_dir} cannot be used for caching as it is not writable."
            warnings.warn(msg, stacklevel=2)
    else:
        cache_dir = Path(os.environ.get("ANSIBLE_HOME", "~/.ansible")).expanduser()
        # This code should be never be reached because import from ansible-core
        #  would trigger a fatal error if this location is not writable.
        if not is_writable(cache_dir):  # pragma: no cover
            msg = f"Cache directory {cache_dir} is not writable."
            raise OSError(msg)

    if not cache_dir:
        # As "project_dir" can also be "/" and user might not be able
        # to write to it, we use a temporary directory as fallback.
        checksum = hashlib.sha256(
            project_dir.as_posix().encode("utf-8"),
        ).hexdigest()[:4]

        cache_dir = Path(tempfile.gettempdir()) / f".ansible-{checksum}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        msg = f"Using unique temporary directory {cache_dir} for caching."
        warnings.warn(msg, stacklevel=2)

    # Ensure basic folder structure exists so `ansible-galaxy list` does not
    # fail with: None of the provided paths were usable. Please specify a valid path with
    try:
        for name in ("roles", "collections"):
            (cache_dir / name).mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover
        msg = "Failed to create cache directory."
        raise RuntimeError(msg) from exc

    # We succeed only if the path is writable.
    return cache_dir
