"""Pytest fixtures."""
import pathlib
from typing import Generator

import pytest

from ansible_compat.runtime import Runtime


@pytest.fixture
# pylint: disable=unused-argument
def runtime(scope: str = "session") -> Generator[Runtime, None, None]:
    """Isolated runtime fixture."""
    instance = Runtime(isolated=True)
    yield instance
    instance.clean()


@pytest.fixture
# pylint: disable=unused-argument
def runtime_tmp(
    tmp_path: pathlib.Path, scope: str = "session"
) -> Generator[Runtime, None, None]:
    """Isolated runtime fixture using a temp directory."""
    instance = Runtime(project_dir=str(tmp_path), isolated=True)
    yield instance
    instance.clean()
