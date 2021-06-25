"""Ansible runtime environment maanger."""
import os
import subprocess
from typing import TYPE_CHECKING, Any, List, Optional, Union

from packaging.version import Version

from ansible_compat.config import AnsibleConfig, parse_ansible_version
from ansible_compat.errors import MissingAnsibleError
from ansible_compat.prerun import get_cache_dir

if TYPE_CHECKING:
    # https://github.com/PyCQA/pylint/issues/3240
    # pylint: disable=unsubscriptable-object
    CompletedProcess = subprocess.CompletedProcess[Any]
else:
    CompletedProcess = subprocess.CompletedProcess


class Runtime:
    """Ansible Runtime manager."""

    _version: Optional[Version] = None
    cache_dir: Optional[str] = None

    def __init__(
        self, project_dir: Optional[str] = None, isolated: bool = False
    ) -> None:
        """Initialize Ansible runtime environment.

        Isolated mode assures that installation of collections or roles
        does not affect Ansible installation, an unique cache directory
        being used instead.
        """
        self.project_dir = project_dir or os.getcwd()
        if isolated:
            self.cache_dir = get_cache_dir(self.project_dir)
        self.config = AnsibleConfig()

    # pylint: disable=no-self-use
    def exec(self, args: Union[str, List[str]]) -> CompletedProcess:
        """Execute a command inside an Ansible environment."""
        return subprocess.run(
            args,
            universal_newlines=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @property
    def version(self) -> Version:
        """Return current Version object for Ansible.

        If version is not mentioned, it returns current version as detected.
        When version argument is mentioned, it return converts the version string
        to Version object in order to make it usable in comparisons.
        """
        if self._version:
            return self._version

        proc = self.exec(["ansible", "--version"])
        if proc.returncode == 0:
            version, error = parse_ansible_version(proc.stdout)
            if error is not None:
                raise MissingAnsibleError(error)
        else:
            msg = "Unable to find a working copy of ansible executable."
            raise MissingAnsibleError(msg, proc=proc)

        self._version = Version(version)
        return self._version

    # def install_collection(self, collection: str) -> None:
    #     """..."""
    #     ...

    # def install_requirements(self, requirement: str) -> None:
    #     """..."""
    #     ...

    # def prepare_environment(
    #     self,
    #     project_dir: Optional[str] = None,
    #     offline: bool = False,
    #     required_collections: Optional[Dict[str, str]] = None,
    # ) -> None:
    #     """..."""
    #     ...
