"""Utilities for configuring ansible runtime environment.

No import of ansible-core must happen within this file!
"""

import hashlib
import os
import platform
import sys
import tempfile
import warnings
from importlib.metadata import version
from pathlib import Path

from packaging.version import Version

# Each ansible-core release supports the three most recent Python releases at
# the time it ships. With two ansible-core releases per year and one Python per
# year, that gives 2.16 -> 3.12, 2.17 -> 3.12, 2.18 -> 3.13, ... 2.20 -> 3.14.
# ansible-core enforces its minimum Python via requires-python but declares no
# maximum, so pip will happily install an old ansible-core on a Python it was
# never tested with. This module is early loaded by tools like ansible-lint,
# so warn even for `ansible-lint --version` if the setup is unsupported.
# See https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html
core_version = Version(version("ansible-core"))
_max_python = (3, 12 + (core_version.minor - 16) // 2)
if sys.version_info[:2] > _max_python:  # pragma: no cover
    msg = (
        f"UNSUPPORTED: ansible-core {core_version} supports Python up to "
        f"{_max_python[0]}.{_max_python[1]} and we found "
        f"{platform.python_version()}. Some features may not work."
    )
    warnings.warn(msg, stacklevel=2)


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
