"""Ansible runtime environment maanger."""
import importlib
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import packaging

from ansible_compat.config import (
    AnsibleConfig,
    ansible_collections_path,
    parse_ansible_version,
)
from ansible_compat.constants import MSG_INVALID_FQRL
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

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        project_dir: Optional[str] = None,
        isolated: bool = False,
        min_required_version: Optional[str] = None,
        require_module: bool = False,
        max_retries: int = 0,
    ) -> None:
        """Initialize Ansible runtime environment.

        :param project_dir: The directory containing the Ansible project. If
                            not mentioned it will be guessed from the current
                            working directory.
        :param isolated: Assure that installation of collections or roles
                         does not affect Ansible installation, an unique cache
                         directory being used instead.
        :param min_required_version: Minimal version of Ansible required. If
                                     not found, a :class:`RuntimeError`
                                     exception is raised.
        :param: require_module: If set, instantiation will fail if Ansible
                                Python module is missing or is not matching
                                the same version as the Ansible command line.
                                That is useful for consumers that expect to
                                also perform Python imports from Ansible.
        :param max_retries: Number of times it should retry network operations.
                            Default is 0, no retries.
        """
        self.project_dir = project_dir or os.getcwd()
        self.isolated = isolated
        self.max_retries = max_retries
        if isolated:
            self.cache_dir = get_cache_dir(self.project_dir)
        self.config = AnsibleConfig()

        if (
            min_required_version is not None
            and packaging.version.Version(min_required_version) > self.version
        ):
            raise RuntimeError(
                f"Found incompatible version of ansible runtime {self.version}, instead of {min_required_version} or newer."
            )
        if require_module:
            self._ensure_module_available()

    def _ensure_module_available(self) -> None:
        """Assure that Ansible Python module is installed and matching CLI version."""
        ansible_release_module = None
        try:
            ansible_release_module = importlib.import_module("ansible.release")
        except (ModuleNotFoundError, ImportError):
            pass

        if ansible_release_module is None:
            raise RuntimeError("Unable to find Ansible python module.")

        ansible_module_version = packaging.version.parse(
            ansible_release_module.__version__  # type: ignore
        )
        if ansible_module_version != self.version:
            raise RuntimeError(
                f"Ansible CLI ({self.version}) and python module"
                f" ({ansible_module_version}) versions do not match. This "
                "indicates a broken execution environment."
            )

    def clean(self) -> None:
        """Remove content of cache_dir."""
        if self.cache_dir:
            shutil.rmtree(self.cache_dir, ignore_errors=True)

    def exec(
        self, args: Union[str, List[str]], retry: bool = False
    ) -> CompletedProcess:
        """Execute a command inside an Ansible environment.

        :param retry: Retry network operations on failures.
        """
        for _ in range(self.max_retries + 1 if retry else 1):
            result = subprocess.run(
                args,
                universal_newlines=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0:
                break
            _logger.warning(
                "Retrying execution failure %s of: %s",
                result.returncode,
                " ".join(args),
            )
        return result

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
            self._version = parse_ansible_version(proc.stdout)
            return self._version

        msg = "Unable to find a working copy of ansible executable."
        raise MissingAnsibleError(msg, proc=proc)

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

        # ansible-galaxy before 2.11 fails to upgrade collection unless --force
        # is present, newer versions do not need it
        if self.version < packaging.version.parse("2.11"):
            cmd.append("--force")

        if destination:
            cmd.extend(["-p", str(destination)])
        cmd.append(f"{collection}")

        _logger.info("Running %s", " ".join(cmd))
        run = self.exec(
            cmd,
            retry=True,
        )
        if run.returncode != 0:
            msg = f"Command returned {run.returncode} code:\n{run.stdout}\n{run.stderr}"
            _logger.error(msg)
            raise InvalidPrerequisiteError(msg)

    def install_requirements(self, requirement: str, retry: bool = False) -> None:
        """Install dependencies from a requirements.yml."""
        if not os.path.exists(requirement):
            return
        reqs_yaml = yaml_from_file(requirement)
        if not isinstance(reqs_yaml, (dict, list)):
            raise InvalidPrerequisiteError(
                f"{requirement} file is not a valid Ansible requirements file."
            )

        if isinstance(reqs_yaml, list) or 'roles' in reqs_yaml:
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
            run = self.exec(cmd, retry=retry)
            if run.returncode != 0:
                _logger.error(run.stdout)
                raise AnsibleCommandError(run)

        # Run galaxy collection install works on v2 requirements.yml
        if "collections" in reqs_yaml:

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
            run = self.exec(cmd, retry=retry)
            if run.returncode != 0:
                _logger.error(run.stdout)
                raise AnsibleCommandError(run)

    def prepare_environment(
        self, required_collections: Optional[Dict[str, str]] = None, retry: bool = False
    ) -> None:
        """Make dependencies available if needed."""
        if required_collections is None:
            required_collections = {}

        self.install_requirements("requirements.yml", retry=retry)

        for name, min_version in required_collections.items():
            self.install_collection(
                f"{name}:>={min_version}",
                destination=f"{self.cache_dir}/collections" if self.cache_dir else None,
            )

        self._prepare_ansible_paths()
        # install role if current project looks like a standalone role
        self._install_galaxy_role(self.project_dir, ignore_errors=True)

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

        paths: List[str] = self.config.collections_paths
        if not paths or not isinstance(paths, list):
            raise InvalidPrerequisiteError(
                f"Unable to determine ansible collection paths. ({paths})"
            )

        if self.cache_dir:
            # if we have a cache dir, we want to be use that would be preferred
            # destination when installing a missing collection
            # https://github.com/PyCQA/pylint/issues/4667
            paths.insert(0, f"{self.cache_dir}/collections")  # pylint: disable=E1101

        for path in paths:
            collpath = os.path.expanduser(
                os.path.join(path, 'ansible_collections', ns, coll)
            )
            if os.path.exists(collpath):
                mpath = os.path.join(collpath, 'MANIFEST.json')
                if not os.path.exists(mpath):
                    msg = f"Found collection at '{collpath}' but missing MANIFEST.json, cannot get info."
                    _logger.fatal(msg)
                    raise InvalidPrerequisiteError(msg)

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
                            msg = f"Found {name} collection {found_version} but {version} or newer is required."
                            _logger.fatal(msg)
                            raise InvalidPrerequisiteError(msg)
                break
        else:
            if install:
                self.install_collection(f"{name}:>={version}")
                self.require_collection(name=name, version=version, install=False)
            else:
                msg = f"Collection '{name}' not found in '{paths}'"
                _logger.fatal(msg)
                raise InvalidPrerequisiteError(msg)

    def _prepare_ansible_paths(self) -> None:
        """Configure Ansible environment variables."""
        try:
            library_paths: List[str] = self.config.default_module_path.copy()
            roles_path: List[str] = self.config.default_roles_path.copy()
            collections_path: List[str] = self.config.collections_paths.copy()
        except AttributeError as exc:
            raise RuntimeError("Unexpected ansible configuration") from exc

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

        if library_paths != self.config.DEFAULT_MODULE_PATH:
            _update_env('ANSIBLE_LIBRARY', library_paths)
        if collections_path != self.config.collections_paths:
            _update_env(ansible_collections_path(), collections_path)
        if roles_path != self.config.default_roles_path:
            _update_env('ANSIBLE_ROLES_PATH', roles_path)

    def _install_galaxy_role(
        self, project_dir: str, role_name_check: int = 0, ignore_errors: bool = False
    ) -> None:
        """Detect standalone galaxy role and installs it.

        :param: role_name_check: logic to used to check role name
            0: exit with error if name is not compliant (default)
            1: warn if name is not compliant
            2: bypass any name checking

        :param: ignore_errors: if True, bypass installing invalid roles.

        Our implementation aims to match ansible-galaxy's behaviour for installing
        roles from a tarball or scm. For example ansible-galaxy will install a role
        that has both galaxy.yml and meta/main.yml present but empty. Also missing
        galaxy.yml is accepted but missing meta/main.yml is not.
        """
        yaml = None
        galaxy_info = {}
        meta_filename = os.path.join(project_dir, 'meta', 'main.yml')

        if not os.path.exists(meta_filename):
            if ignore_errors:
                return
        else:
            yaml = yaml_from_file(meta_filename)

        if yaml and 'galaxy_info' in yaml:
            galaxy_info = yaml['galaxy_info']

        fqrn = _get_role_fqrn(galaxy_info, project_dir)

        if role_name_check in [0, 1]:
            if not re.match(r"[a-z0-9][a-z0-9_]+\.[a-z][a-z0-9_]+$", fqrn):
                msg = MSG_INVALID_FQRL.format(fqrn)
                if role_name_check == 1:
                    _logger.warning(msg)
                else:
                    _logger.error(msg)
                    raise InvalidPrerequisiteError(msg)
        else:
            # when 'role-name' is in skip_list, we stick to plain role names
            if 'role_name' in galaxy_info:
                role_namespace = _get_galaxy_role_ns(galaxy_info)
                role_name = _get_galaxy_role_name(galaxy_info)
                fqrn = f"{role_namespace}{role_name}"
            else:
                fqrn = pathlib.Path(project_dir).absolute().name
        path = pathlib.Path(os.path.expanduser(self.config.default_roles_path[0]))
        path.mkdir(parents=True, exist_ok=True)
        link_path = path / fqrn
        # despite documentation stating that is_file() reports true for symlinks,
        # it appears that is_dir() reports true instead, so we rely on exists().
        target = pathlib.Path(project_dir).absolute()
        exists = link_path.exists() or link_path.is_symlink()
        if not exists or os.readlink(link_path) != str(target):
            if exists:
                link_path.unlink()
            link_path.symlink_to(str(target), target_is_directory=True)
        _logger.info(
            "Using %s symlink to current repository in order to enable Ansible to find the role using its expected full name.",
            link_path,
        )


def _get_role_fqrn(galaxy_infos: Dict[str, Any], project_dir: str) -> str:
    """Compute role fqrn."""
    role_namespace = _get_galaxy_role_ns(galaxy_infos)
    role_name = _get_galaxy_role_name(galaxy_infos)

    if len(role_name) == 0:
        role_name = pathlib.Path(project_dir).absolute().name
        role_name = re.sub(r'(ansible-|ansible-role-)', '', role_name).split(
            ".", maxsplit=2
        )[-1]

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
    if not role_namespace or re.match(r"^\w+ \w+", role_namespace):
        role_namespace = ""
    else:
        role_namespace = f"{role_namespace}."
    return role_namespace


def _get_galaxy_role_name(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role name from meta/main.yml."""
    return galaxy_infos.get('role_name', "")
