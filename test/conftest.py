"""Pytest fixtures."""
from typing import Generator

import pytest

from ansible_compat.runtime import Runtime


@pytest.fixture
# pylint: disable=unused-argument
def runtime(scope: str = "session") -> Generator[Runtime, None, None]:
    """Runtime fixture."""
    instance = Runtime(isolated=True)
    yield instance
    instance.clean()
