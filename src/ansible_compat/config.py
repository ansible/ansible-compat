"""Store configuration options as a singleton."""
import ast
import copy
import os
import re
import subprocess
from collections import UserDict
from functools import lru_cache
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from packaging.version import Version

from ansible_compat.errors import MissingAnsibleError

if TYPE_CHECKING:
    # https://github.com/PyCQA/pylint/issues/3285
    _UserDict = UserDict[str, object]  # pylint: disable=unsubscriptable-object
else:
    _UserDict = UserDict


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
            raise MissingAnsibleError()
    else:
        print(
            "Unable to find a working copy of ansible executable.",
            proc,
        )
        raise MissingAnsibleError()
    return Version(version)


class AnsibleConfig(_UserDict):  # pylint: disable=too-many-ancestors
    """Interface to query Ansible configuration.

    This should allow user to access everything provided by `ansible-config dump` without having to parse the data himself.
    """

    _aliases = {
        'COLLECTIONS_PATHS': 'COLLECTIONS_PATH',  # 2.9 -> 2.10+
        'COLLECTIONS_PATH': 'COLLECTIONS_PATHS',  # 2.10+ -> 2.9
    }

    def __init__(
        self,
        config_dump: Optional[str] = None,
        data: Optional[Dict[str, object]] = None,
    ) -> None:
        """Load config dictionary."""
        super().__init__()

        if data:
            self.data = copy.copy(data)
            return

        if not config_dump:
            env = os.environ.copy()
            # Avoid possible ANSI garbage
            env["ANSIBLE_FORCE_COLOR"] = "0"
            config_dump = subprocess.check_output(
                ["ansible-config", "dump"], universal_newlines=True, env=env
            )

        for match in re.finditer(
            r"^(?P<key>[A-Za-z0-9_]+).* = (?P<value>.*)$", config_dump, re.MULTILINE
        ):
            key = match.groupdict()['key']
            value = match.groupdict()['value']
            try:
                self[key] = ast.literal_eval(value)
            except (NameError, SyntaxError, ValueError):
                self[key] = value

    def __getattr__(self, attr_name: str) -> object:
        """Allow access of config options as attributes."""
        name = attr_name.upper()
        if name in self.data:
            return self.data[name]
        if name in self._aliases:
            return self.data[self._aliases[name]]
        raise AttributeError(attr_name)

    def __getitem__(self, name: str) -> object:
        """Allow access to config options using indexing."""
        return super().__getitem__(name.upper())

    def __copy__(self) -> "AnsibleConfig":
        """Allow users to run copy on Config."""
        return AnsibleConfig(data=self.data)

    def __deepcopy__(self, memo: object) -> "AnsibleConfig":
        """Allow users to run deeepcopy on Config."""
        return AnsibleConfig(data=self.data)
