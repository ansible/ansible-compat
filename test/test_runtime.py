"""Tests for Runtime class."""
import pytest
from packaging.version import Version
from pytest_mock import MockerFixture

from ansible_compat.runtime import Runtime


def test_runtime_version() -> None:
    """Tests version property."""
    runtime = Runtime()
    version = runtime.version
    assert isinstance(version, Version)
    # tests that caching property value worked (coverage)
    assert version == runtime.version


def test_runtime_version_fail(mocker: MockerFixture) -> None:
    """Tests for failure to detect Ansible version."""
    mocker.patch(
        "ansible_compat.runtime.parse_ansible_version",
        return_value=("", "some error"),
        autospec=True,
    )
    runtime = Runtime()
    with pytest.raises(RuntimeError) as exc:
        _ = runtime.version
    assert exc.value.args[0] == "some error"
