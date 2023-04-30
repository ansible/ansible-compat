"""Pytest fixtures."""
import pathlib
from collections.abc import Generator

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
