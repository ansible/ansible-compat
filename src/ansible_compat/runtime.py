"""Ansible runtime environment maanger."""
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import packaging

from ansible_compat._compat import retry
from ansible_compat.config import (
    AnsibleConfig,
    ansible_collections_path,
    parse_ansible_version,
)
from ansible_compat.constants import (  # INVALID_CONFIG_RC,
    ANSIBLE_DEFAULT_ROLES_PATH,
    MSG_INVALID_FQRL,
)
from ansible_compat.errors import (
    AnsibleCommandError,
    AnsibleCompatError,
    InvalidPrerequisiteError,
    MissingAnsibleError,
)
from ansible_compat.loaders import yaml_from_file
from ansible_compat.prerun import get_cache_dir

if TYPE_CHECKING:
    # https://github.com/PyCQA/pylint/issues/3240
    # pylint: disable=unsubscriptable-object
    CompletedProcess = subprocess.CompletedProcess[Any]
else:
    CompletedProcess = subprocess.CompletedProcess

_logger = logging.getLogger(__name__)


class Runtime:
    """Ansible Runtime manager."""

    _version: Optional[packaging.version.Version] = None
    cache_dir: Optional[str] = None
    collections_path: List[str]

    def __init__(
        self, project_dir: Optional[str] = None, isolated: bool = False
    ) -> None:
        """Initialize Ansible runtime environment.

        Isolated mode assures that installation of collections or roles
        does not affect Ansible installation, an unique cache directory
        being used instead.
        """
        self.project_dir = project_dir or os.getcwd()
        self.isolated = isolated
        if isolated:
            self.cache_dir = get_cache_dir(self.project_dir)
        self.config = AnsibleConfig()

    def clean(self) -> None:
        """Remove content of cache_dir."""
        if self.cache_dir:
            shutil.rmtree(self.cache_dir, ignore_errors=True)

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
    def version(self) -> packaging.version.Version:
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

        self._version = packaging.version.Version(version)
        return self._version

    def install_collection(
        self, collection: str, destination: Optional[Union[str, pathlib.Path]] = None
    ) -> None:
        """Install an Ansible collection.

        Can accept version constraints like 'foo.bar:>=1.2.3'
        """
        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            "-v",
        ]
        if destination:
            cmd.extend(["-p", str(destination)])
        cmd.append(f"{collection}")

        _logger.info("Running %s", " ".join(cmd))
        run = subprocess.run(
            cmd,
            universal_newlines=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if run.returncode != 0:
            _logger.error("Command returned %s code:\n%s", run.returncode, run.stdout)
            raise InvalidPrerequisiteError()

    @retry
    def install_requirements(self, requirement: str) -> None:
        """Install dependencies from a requirements.yml."""
        if not os.path.exists(requirement):
            return

        cmd = [
            "ansible-galaxy",
            "role",
            "install",
            "-vr",
            f"{requirement}",
        ]
        if self.cache_dir:
            cmd.extend(["--roles-path", f"{self.cache_dir}/roles"])

        _logger.info("Running %s", " ".join(cmd))
        run = subprocess.run(
            cmd,
            universal_newlines=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if run.returncode != 0:
            _logger.error(run.stdout)
            raise AnsibleCommandError(run)

        # Run galaxy collection install works on v2 requirements.yml
        if "collections" in yaml_from_file(requirement):

            cmd = [
                "ansible-galaxy",
                "collection",
                "install",
                "-vr",
                f"{requirement}",
            ]
            if self.cache_dir:
                cmd.extend(["-p", f"{self.cache_dir}/collections"])

            _logger.info("Running %s", " ".join(cmd))
            run = subprocess.run(
                cmd,
                universal_newlines=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if run.returncode != 0:
                _logger.error(run.stdout)
                raise AnsibleCommandError(run)

    def prepare_environment(
        self,
        offline: bool = False,
        required_collections: Optional[Dict[str, str]] = None,
    ) -> None:
        """Make dependencies available if needed."""
        if required_collections is None:
            required_collections = {}

        if not offline:
            self.install_requirements("requirements.yml")
            for req in pathlib.Path(".").glob("molecule/*/requirements.yml"):
                self.install_requirements(str(req))

        for name, min_version in required_collections.items():
            self.install_collection(
                f"{name}:>={min_version}",
                destination=f"{self.cache_dir}/collections" if self.cache_dir else None,
            )

        _install_galaxy_role(self.project_dir)
        # _perform_mockings()
        self._prepare_ansible_paths()

    def require_collection(  # noqa: C901
        self,
        name: str,
        version: Optional[str] = None,
        install: bool = True,
    ) -> None:
        """Check if a minimal collection version is present or exits.

        In the future this method may attempt to install a missing or outdated
        collection before failing.
        """
        try:
            ns, coll = name.split('.', 1)
        except ValueError as exc:
            raise InvalidPrerequisiteError(
                "Invalid collection name supplied: %s" % name
            ) from exc

        paths = self.config.collections_path
        if not paths or not isinstance(paths, list):
            raise InvalidPrerequisiteError(
                f"Unable to determine ansible collection paths. ({paths})"
            )

        if self.cache_dir:
            # if we have a cache dir, we want to be use that would be preferred
            # destination when installing a missing collection
            paths.insert(0, f"{self.cache_dir}/collections")

        for path in paths:
            collpath = os.path.join(path, 'ansible_collections', ns, coll)
            if os.path.exists(collpath):
                mpath = os.path.join(collpath, 'MANIFEST.json')
                if not os.path.exists(mpath):
                    _logger.fatal(
                        "Found collection at '%s' but missing MANIFEST.json, cannot get info.",
                        collpath,
                    )
                    raise InvalidPrerequisiteError()

                with open(mpath, 'r') as f:
                    manifest = json.loads(f.read())
                    found_version = packaging.version.parse(
                        manifest['collection_info']['version']
                    )
                    if version and found_version < packaging.version.parse(version):
                        if install:
                            self.install_collection(f"{name}:>={version}")
                            self.require_collection(name, version, install=False)
                        else:
                            _logger.fatal(
                                "Found %s collection %s but %s or newer is required.",
                                name,
                                found_version,
                                version,
                            )
                            raise InvalidPrerequisiteError()
                break
        else:
            if install:
                self.install_collection(f"{name}:>={version}")
                self.require_collection(name=name, version=version, install=False)
            else:
                _logger.fatal("Collection '%s' not found in '%s'", name, paths)
                raise InvalidPrerequisiteError()

    def _prepare_ansible_paths(self) -> None:
        """Configure Ansible environment variables."""
        library_paths: List[str] = []
        roles_path: List[str] = []
        collections_path = self.config.collections_path
        if not isinstance(collections_path, list):
            raise RuntimeError(f"Unexpected collection_path value: {collections_path}")

        alterations_list = [
            (library_paths, "plugins/modules", True),
            (roles_path, "roles", True),
        ]

        if self.isolated:
            alterations_list.extend(
                [
                    (roles_path, f"{self.cache_dir}/roles", False),
                    (library_paths, f"{self.cache_dir}/modules", False),
                    (collections_path, f"{self.cache_dir}/collections", False),
                ]
            )

        for path_list, path, must_be_present in alterations_list:
            if must_be_present and not os.path.exists(path):
                continue
            if path not in path_list:
                path_list.insert(0, path)

        _update_env('ANSIBLE_LIBRARY', library_paths)
        _update_env(ansible_collections_path(), collections_path)
        _update_env(
            'ANSIBLE_ROLES_PATH', roles_path, default=ANSIBLE_DEFAULT_ROLES_PATH
        )


def _install_galaxy_role(project_dir: str, role_name_check: int = 0) -> None:
    """Detect standalone galaxy role and installs it.

    role_name_check levels:
    0: exit with error if name is not compliant (default)
    1: warn if name is not compliant
    2: bypass any name checking
    """
    if not os.path.exists("meta/main.yml"):
        return
    yaml = yaml_from_file("meta/main.yml")
    if 'galaxy_info' not in yaml:
        return

    fqrn = _get_role_fqrn(yaml['galaxy_info'])

    if role_name_check in [0, 1]:
        if not re.match(r"[a-z0-9][a-z0-9_]+\.[a-z][a-z0-9_]+$", fqrn):
            msg = MSG_INVALID_FQRL.format(fqrn)
            if role_name_check == 1:
                _logger.warning(msg)
            else:
                _logger.error(msg)
                raise InvalidPrerequisiteError()
    else:
        # when 'role-name' is in skip_list, we stick to plain role names
        if 'role_name' in yaml['galaxy_info']:
            role_namespace = _get_galaxy_role_ns(yaml['galaxy_info'])
            role_name = _get_galaxy_role_name(yaml['galaxy_info'])
            fqrn = f"{role_namespace}{role_name}"
        else:
            fqrn = pathlib.Path(".").absolute().name
    path = pathlib.Path(f"{get_cache_dir(project_dir)}/roles")
    path.mkdir(parents=True, exist_ok=True)
    link_path = path / fqrn
    # despite documentation stating that is_file() reports true for symlinks,
    # it appears that is_dir() reports true instead, so we rely on exists().
    target = pathlib.Path(project_dir).absolute()
    if not link_path.exists() or os.readlink(link_path) != str(target):
        if link_path.exists():
            link_path.unlink()
        link_path.symlink_to(target, target_is_directory=True)
    _logger.info(
        "Using %s symlink to current repository in order to enable Ansible to find the role using its expected full name.",
        link_path,
    )


def _get_role_fqrn(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role fqrn."""
    role_namespace = _get_galaxy_role_ns(galaxy_infos)
    role_name = _get_galaxy_role_name(galaxy_infos)
    if len(role_name) == 0:
        role_name = pathlib.Path(".").absolute().name
        role_name = re.sub(r'(ansible-|ansible-role-)', '', role_name)

    return f"{role_namespace}{role_name}"


def _update_env(varname: str, value: List[str], default: str = "") -> None:
    """Update colon based environment variable if needed.

    New values are added by inserting them to assure they take precedence
    over the existing ones.
    """
    if value:
        orig_value = os.environ.get(varname, default=default)
        if orig_value:
            # Prepend original or default variable content to custom content.
            value = [*value, *orig_value.split(':')]
        value_str = ":".join(value)
        if value_str != os.environ.get(varname, ""):
            os.environ[varname] = value_str
            _logger.info("Added %s=%s", varname, value_str)


def _get_galaxy_role_ns(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role namespace from meta/main.yml, including trailing dot."""
    role_namespace = galaxy_infos.get('namespace', "")
    if len(role_namespace) == 0:
        role_namespace = galaxy_infos.get('author', "")
    if not isinstance(role_namespace, str):
        raise AnsibleCompatError(
            "Role namespace must be string, not %s" % role_namespace
        )
    # if there's a space in the name space, it's likely author name
    # and not the galaxy login, so act as if there was no namespace
    if re.match(r"^\w+ \w+", role_namespace):
        role_namespace = ""
    else:
        role_namespace = f"{role_namespace}."
    return role_namespace


def _get_galaxy_role_name(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role name from meta/main.yml."""
    return galaxy_infos.get('role_name', "")
