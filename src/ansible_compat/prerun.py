"""Utilities for configuring ansible runtime environment."""
import hashlib
import os


def get_cache_dir(project_dir: str) -> str:
    """Compute cache directory to be used based on project path."""
    # 6 chars of entropy should be enough
    cache_key = hashlib.sha256(os.path.abspath(project_dir).encode()).hexdigest()[:6]
    cache_dir = "%s/ansible-compat/%s" % (
        os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
        cache_key,
    )
    return cache_dir
