"""Store configuration options as a singleton."""
import os
import re
import subprocess
import sys
from functools import lru_cache
from typing import List, Optional, Tuple

from packaging.version import Version

from ansible_compat.constants import ANSIBLE_MISSING_RC

# Used to store collection list paths (with mock paths if needed)
collection_list: List[str] = []


@lru_cache()
def ansible_collections_path() -> str:
    """Return collection path variable for current version of Ansible."""
    # respect Ansible behavior, which is to load old name if present
    for env_var in ["ANSIBLE_COLLECTIONS_PATHS", "ANSIBLE_COLLECTIONS_PATH"]:
        if env_var in os.environ:
            return env_var

    # https://github.com/ansible/ansible/pull/70007
    if ansible_version() >= ansible_version("2.10.0.dev0"):
        return "ANSIBLE_COLLECTIONS_PATH"
    return "ANSIBLE_COLLECTIONS_PATHS"


def parse_ansible_version(stdout: str) -> Tuple[str, Optional[str]]:
    """Parse output of 'ansible --version'."""
    # Ansible can produce extra output before displaying version in debug mode.

    # ansible-core 2.11+: 'ansible [core 2.11.3]'
    match = re.search(
        r"^ansible \[(?:core|base) (?P<version>[^\]]+)\]", stdout, re.MULTILINE
    )
    if match:
        return match.group("version"), None
    # ansible-base 2.10 and Ansible 2.9: 'ansible 2.x.y'
    match = re.search(r"^ansible (?P<version>[^\s]+)", stdout, re.MULTILINE)
    if match:
        return match.group("version"), None
    return "", "FATAL: Unable parse ansible cli version: %s" % stdout


@lru_cache()
def ansible_version(version: str = "") -> Version:
    """Return current Version object for Ansible.

    If version is not mentioned, it returns current version as detected.
    When version argument is mentioned, it return converts the version string
    to Version object in order to make it usable in comparisons.
    """
    if version:
        return Version(version)

    proc = subprocess.run(
        ["ansible", "--version"],
        universal_newlines=True,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode == 0:
        version, error = parse_ansible_version(proc.stdout)
        if error is not None:
            print(error)
            sys.exit(ANSIBLE_MISSING_RC)
    else:
        print(
            "Unable to find a working copy of ansible executable.",
            proc,
        )
        sys.exit(ANSIBLE_MISSING_RC)
    return Version(version)


if ansible_collections_path() in os.environ:
    collection_list = os.environ[ansible_collections_path()].split(':')
