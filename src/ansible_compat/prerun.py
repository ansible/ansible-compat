"""Utilities for configuring ansible runtime environment."""
import hashlib
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple, Type, Union

import packaging
import tenacity

from ansible_compat.config import (
    ansible_collections_path,
    collection_list,
    parse_ansible_version,
)
from ansible_compat.constants import (  # INVALID_CONFIG_RC,
    ANSIBLE_DEFAULT_ROLES_PATH,
    ANSIBLE_MIN_VERSION,
    ANSIBLE_MISSING_RC,
    INVALID_PREREQUISITES_RC,
    MSG_INVALID_FQRL,
)
from ansible_compat.loaders import yaml_from_file

_logger = logging.getLogger(__name__)


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


def install_collection(collection: str, destination: Optional[str] = None) -> None:
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
        cmd.extend(["-p", destination])
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
        sys.exit(INVALID_PREREQUISITES_RC)


@tenacity.retry(  # Retry up to 3 times as galaxy server can return errors
    reraise=True,
    wait=tenacity.wait_fixed(30),  # type: ignore
    stop=tenacity.stop_after_attempt(3),  # type: ignore
    before_sleep=tenacity.after_log(_logger, logging.WARNING),  # type: ignore
)
def install_requirements(requirement: str, cache_dir) -> None:
    """Install dependencies from a requirements.yml."""
    if not os.path.exists(requirement):
        return

    cmd = [
        "ansible-galaxy",
        "role",
        "install",
        "--roles-path",
        f"{cache_dir}/roles",
        "-vr",
        f"{requirement}",
    ]

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
        raise RuntimeError(run.returncode)

    # Run galaxy collection install works on v2 requirements.yml
    if "collections" in yaml_from_file(requirement):

        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            "-p",
            f"{cache_dir}/collections",
            "-vr",
            f"{requirement}",
        ]

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
            raise RuntimeError(run.returncode)


def get_cache_dir(project_dir: str) -> str:
    """Compute cache directory to be used based on project path."""
    # 6 chars of entropy should be enough
    cache_key = hashlib.sha256(os.path.abspath(project_dir).encode()).hexdigest()[:6]
    cache_dir = "%s/ansible-compat/%s" % (
        os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
        cache_key,
    )
    return cache_dir


def prepare_environment(
    project_dir: Optional[str] = None,
    offline: bool = False,
    required_collections: Optional[Dict[str, str]] = None,
) -> None:
    """Make dependencies available if needed."""
    if required_collections is None:
        required_collections = {}

    if not project_dir:
        project_dir = os.getcwd()
    cache_dir = get_cache_dir(project_dir)

    if not offline:
        install_requirements("requirements.yml", cache_dir=cache_dir)
        for req in pathlib.Path(".").glob("molecule/*/requirements.yml"):
            install_requirements(str(req), cache_dir=cache_dir)

    for name, min_version in required_collections.items():
        install_collection(
            f"{name}:>={min_version}",
            destination=f"{cache_dir}/collections" if cache_dir else None,
        )

    _install_galaxy_role(project_dir)
    # _perform_mockings()
    _prepare_ansible_paths(cache_dir=cache_dir)


def _get_galaxy_role_ns(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role namespace from meta/main.yml, including trailing dot."""
    role_namespace = galaxy_infos.get('namespace', "")
    if len(role_namespace) == 0:
        role_namespace = galaxy_infos.get('author', "")
    if not isinstance(role_namespace, str):
        raise RuntimeError("Role namespace must be string, not %s" % role_namespace)
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


def _get_role_fqrn(galaxy_infos: Dict[str, Any]) -> str:
    """Compute role fqrn."""
    role_namespace = _get_galaxy_role_ns(galaxy_infos)
    role_name = _get_galaxy_role_name(galaxy_infos)
    if len(role_name) == 0:
        role_name = pathlib.Path(".").absolute().name
        role_name = re.sub(r'(ansible-|ansible-role-)', '', role_name)

    return f"{role_namespace}{role_name}"


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
                sys.exit(INVALID_PREREQUISITES_RC)
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
    # it appears that is_dir() reports true instead, so we rely on exits().
    target = pathlib.Path(project_dir).absolute()
    if not link_path.exists() or os.readlink(link_path) != str(target):
        if link_path.exists():
            link_path.unlink()
        link_path.symlink_to(target, target_is_directory=True)
    _logger.info(
        "Using %s symlink to current repository in order to enable Ansible to find the role using its expected full name.",
        link_path,
    )


def _prepare_ansible_paths(cache_dir: str) -> None:
    """Configure Ansible environment variables."""
    library_paths: List[str] = []
    roles_path: List[str] = []

    for path_list, path in (
        (library_paths, "plugins/modules"),
        (library_paths, f"{cache_dir}/modules"),
        (collection_list, f"{cache_dir}/collections"),
        (roles_path, "roles"),
        (roles_path, f"{cache_dir}/roles"),
    ):
        if path not in path_list and os.path.exists(path):
            path_list.append(path)

    _update_env('ANSIBLE_LIBRARY', library_paths)
    _update_env(ansible_collections_path(), collection_list)
    _update_env('ANSIBLE_ROLES_PATH', roles_path, default=ANSIBLE_DEFAULT_ROLES_PATH)


def _update_env(varname: str, value: List[str], default: str = "") -> None:
    """Update colon based environment variable if needed. by appending."""
    if value:
        orig_value = os.environ.get(varname, default=default)
        if orig_value:
            # Prepend original or default variable content to custom content.
            value = [*orig_value.split(':'), *value]
        value_str = ":".join(value)
        if value_str != os.environ.get(varname, ""):
            os.environ[varname] = value_str
            _logger.info("Added %s=%s", varname, value_str)


def ansible_config_get(key: str, kind: Type[Any] = str) -> Union[str, List[str], None]:
    """Return configuration item from ansible config."""
    env = os.environ.copy()
    # Avoid possible ANSI garbage
    env["ANSIBLE_FORCE_COLOR"] = "0"
    # Avoid our own override as this prevents returning system paths.
    colpathvar = ansible_collections_path()
    if colpathvar in env:
        env.pop(colpathvar)

    config = subprocess.check_output(
        ["ansible-config", "dump"], universal_newlines=True, env=env
    )

    if kind == str:
        result = re.search(rf"^{key}.* = (.*)$", config, re.MULTILINE)
        if result:
            return result.groups()[0]
    elif kind == list:
        result = re.search(rf"^{key}.* = (\[.*\])$", config, re.MULTILINE)
        if result:
            val = eval(result.groups()[0])  # pylint: disable=eval-used
            if not isinstance(val, list):
                raise RuntimeError(f"Unexpected data read for {key}: {val}")
            return val
    else:
        raise RuntimeError("Unknown data type.")
    return None


def require_collection(  # noqa: C901
    name: str,
    version: Optional[str] = None,
    install: bool = True,
    cache_dir: Optional[str] = None,
) -> None:
    """Check if a minimal collection version is present or exits.

    In the future this method may attempt to install a missing or outdated
    collection before failing.
    """
    try:
        ns, coll = name.split('.', 1)
    except ValueError:
        sys.exit("Invalid collection name supplied: %s" % name)

    paths = ansible_config_get('COLLECTIONS_PATHS', list)
    if not paths or not isinstance(paths, list):
        sys.exit(f"Unable to determine ansible collection paths. ({paths})")

    if cache_dir:
        # if we have a cache dir, we want to be use that would be preferred
        # destination when installing a missing collection
        paths.insert(0, f"{cache_dir}/collections")

    for path in paths:
        collpath = os.path.join(path, 'ansible_collections', ns, coll)
        if os.path.exists(collpath):
            mpath = os.path.join(collpath, 'MANIFEST.json')
            if not os.path.exists(mpath):
                _logger.fatal(
                    "Found collection at '%s' but missing MANIFEST.json, cannot get info.",
                    collpath,
                )
                sys.exit(INVALID_PREREQUISITES_RC)

            with open(mpath, 'r') as f:
                manifest = json.loads(f.read())
                found_version = packaging.version.parse(
                    manifest['collection_info']['version']
                )
                if version and found_version < packaging.version.parse(version):
                    if install:
                        install_collection(f"{name}:>={version}")
                        require_collection(name, version, install=False)
                    else:
                        _logger.fatal(
                            "Found %s collection %s but %s or newer is required.",
                            name,
                            found_version,
                            version,
                        )
                        sys.exit(INVALID_PREREQUISITES_RC)
            break
    else:
        if install:
            install_collection(f"{name}:>={version}")
            require_collection(
                name=name, version=version, install=False, cache_dir=cache_dir
            )
        else:
            _logger.fatal("Collection '%s' not found in '%s'", name, paths)
            sys.exit(INVALID_PREREQUISITES_RC)
