"""Utilities for configuring ansible runtime environment."""
import hashlib
import logging
import os
import subprocess
import sys
from functools import lru_cache
from typing import Tuple

import packaging

from ansible_compat.config import parse_ansible_version
from ansible_compat.constants import (  # INVALID_CONFIG_RC,
    ANSIBLE_MIN_VERSION,
    ANSIBLE_MISSING_RC,
)

_logger = logging.getLogger(__name__)
SENTINEL = object()


def check_ansible_presence(exit_on_error: bool = False) -> Tuple[str, str]:
    """Assures we stop execution if Ansible is missing or outdated.

    Return found version and an optional exception if something wrong
    was detected.
    """

    @lru_cache()
    def _get_ver_err() -> Tuple[str, str]:

        err = ""
        failed = False
        ver = ""
        result = subprocess.run(
            args=["ansible", "--version"],
            stdout=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
        if result.returncode != 0:
            return (
                ver,
                "FATAL: Unable to retrieve ansible cli version: %s" % result.stdout,
            )

        ver, error = parse_ansible_version(result.stdout)
        if error is not None:
            return "", error
        try:
            # pylint: disable=import-outside-toplevel
            from ansible.release import __version__ as ansible_module_version

            if packaging.version.parse(
                ansible_module_version
            ) < packaging.version.parse(ANSIBLE_MIN_VERSION):
                failed = True
        except (ImportError, ModuleNotFoundError) as exc:
            failed = True
            ansible_module_version = "none"
            err += f"{exc}\n"
        if failed:
            err += (
                "FATAL: We require a version of Ansible package"
                " >= %s, but %s was found. "
                "Please install a compatible version using the same python interpreter. See "
                "https://docs.ansible.com/ansible/latest/installation_guide"
                "/intro_installation.html#installing-ansible-with-pip"
                % (ANSIBLE_MIN_VERSION, ansible_module_version)
            )

        elif ver != ansible_module_version:
            err = (
                f"FATAL: Ansible CLI ({ver}) and python module"
                f" ({ansible_module_version}) versions do not match. This "
                "indicates a broken execution environment."
            )
        return ver, err

    ver, err = _get_ver_err()
    if exit_on_error and err:
        _logger.error(err)
        sys.exit(ANSIBLE_MISSING_RC)
    return ver, err


def get_cache_dir(project_dir: str) -> str:
    """Compute cache directory to be used based on project path."""
    # 6 chars of entropy should be enough
    cache_key = hashlib.sha256(os.path.abspath(project_dir).encode()).hexdigest()[:6]
    cache_dir = "%s/ansible-compat/%s" % (
        os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
        cache_key,
    )
    return cache_dir
