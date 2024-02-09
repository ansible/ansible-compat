"""Pytest fixtures."""

import importlib.metadata
import json
import pathlib
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Callable

import pytest

from ansible_compat.runtime import Runtime


@pytest.fixture()
# pylint: disable=unused-argument
def runtime(scope: str = "session") -> Generator[Runtime, None, None]:  # noqa: ARG001
    """Isolated runtime fixture."""
    instance = Runtime(isolated=True)
    yield instance
    instance.clean()


@pytest.fixture()
# pylint: disable=unused-argument
def runtime_tmp(
    tmp_path: pathlib.Path,
    scope: str = "session",  # noqa: ARG001
) -> Generator[Runtime, None, None]:
    """Isolated runtime fixture using a temp directory."""
    instance = Runtime(project_dir=tmp_path, isolated=True)
    yield instance
    instance.clean()


def query_pkg_version(pkg: str) -> str:
    """Get the version of a current installed package.

    :param pkg: Package name
    :return: Package version
    """
    return importlib.metadata.version(pkg)


@pytest.fixture()
def pkg_version() -> Callable[[str], str]:
    """Get the version of a current installed package.

    :return: Callable function to get package version
    """
    return query_pkg_version


class VirtualEnvironment:
    """Virtualenv wrapper."""

    def __init__(self, path: Path) -> None:
        """Initialize.

        :param path: Path to virtualenv
        """
        self.project = path
        self.venv_path = self.project / "venv"
        self.venv_bin_path = self.venv_path / "bin"
        self.venv_python_path = self.venv_bin_path / "python"

    def create(self) -> None:
        """Create virtualenv."""
        cmd = [str(sys.executable), "-m", "venv", str(self.venv_path)]
        subprocess.check_call(args=cmd)
        # Install this package into the virtual environment
        self.install(f"{__file__}/../..")

    def install(self, *packages: str) -> None:
        """Install packages in virtualenv.

        :param packages: Packages to install
        """
        cmd = [str(self.venv_python_path), "-m", "pip", "install", *packages]
        subprocess.check_call(args=cmd)

    def python_script_run(self, script: str) -> subprocess.CompletedProcess[str]:
        """Run command in project dir using venv.

        :param args: Command to run
        """
        proc = subprocess.run(
            args=[self.venv_python_path, "-c", script],
            capture_output=True,
            cwd=self.project,
            check=False,
            text=True,
        )
        return proc

    def site_package_dirs(self) -> list[Path]:
        """Get site packages.

        :return: List of site packages dirs
        """
        script = "import json, site; print(json.dumps(site.getsitepackages()))"
        proc = subprocess.run(
            args=[self.venv_python_path, "-c", script],
            capture_output=True,
            check=False,
            text=True,
        )
        dirs = json.loads(proc.stdout)
        if not isinstance(dirs, list):
            msg = "Expected list of site packages"
            raise TypeError(msg)
        sanitized = list({Path(d).resolve() for d in dirs})
        return sanitized


@pytest.fixture(scope="module")
def venv_module(tmp_path_factory: pytest.TempPathFactory) -> VirtualEnvironment:
    """Create a virtualenv in a temporary directory.

    :param tmp_path: pytest fixture for temp path
    :return: VirtualEnvironment instance
    """
    test_project = tmp_path_factory.mktemp(basename="test_project-", numbered=True)
    _venv = VirtualEnvironment(test_project)
    _venv.create()
    return _venv
