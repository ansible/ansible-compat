"""Utilities for configuring ansible runtime environment."""
import hashlib
import os
from pathlib import Path


def get_cache_dir(project_dir: Path) -> Path:
    """Compute cache directory to be used based on project path."""
    # we only use the basename instead of the full path in order to ensure that
    # we would use the same key regardless the location of the user home
    # directory or where the project is clones (as long the project folder uses
    # the same name).
    basename = project_dir.resolve().name.encode(encoding="utf-8")
    # 6 chars of entropy should be enough
    cache_key = hashlib.sha256(basename).hexdigest()[:6]
    cache_dir = (
        Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser()
        / "ansible-compat"
        / cache_key
    )
    return cache_dir
