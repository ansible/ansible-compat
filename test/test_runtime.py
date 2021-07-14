"""Tests for Runtime class."""
# pylint: disable=protected-access
import logging
import os
import pathlib
import subprocess
from contextlib import contextmanager
from typing import Iterator, List

import pytest
from _pytest.monkeypatch import MonkeyPatch
from flaky import flaky
from packaging.version import Version
from pytest_mock import MockerFixture

from ansible_compat.constants import INVALID_PREREQUISITES_RC
from ansible_compat.errors import AnsibleCompatError, InvalidPrerequisiteError
from ansible_compat.runtime import Runtime, _update_env


def test_runtime_version(runtime: Runtime) -> None:
    """Tests version property."""
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
    with pytest.raises(RuntimeError, match="some error"):
        runtime.version  # pylint: disable=pointless-statement


@contextmanager
def remember_cwd(cwd: str) -> Iterator[None]:
    """Context manager for chdir."""
    curdir = os.getcwd()
    try:
        os.chdir(cwd)
        yield
    finally:
        os.chdir(curdir)


# # https://github.com/box/flaky/issues/170
@flaky(max_runs=3)  # type: ignore
def test_prerun_reqs_v1(caplog: pytest.LogCaptureFixture, runtime: Runtime) -> None:
    """Checks that the linter can auto-install requirements v1 when found."""
    cwd = os.path.realpath(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "examples", "reqs_v1"
        )
    )
    with remember_cwd(cwd):
        with caplog.at_level(logging.INFO):
            runtime.prepare_environment()
    assert any(
        msg.startswith("Running ansible-galaxy role install") for msg in caplog.messages
    )
    assert all(
        "Running ansible-galaxy collection install" not in msg
        for msg in caplog.messages
    )


@flaky(max_runs=3)  # type: ignore
def test_prerun_reqs_v2(caplog: pytest.LogCaptureFixture, runtime: Runtime) -> None:
    """Checks that the linter can auto-install requirements v2 when found."""
    cwd = os.path.realpath(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "..", "examples", "reqs_v2"
        )
    )
    with remember_cwd(cwd):
        with caplog.at_level(logging.INFO):
            runtime.prepare_environment()
        assert any(
            msg.startswith("Running ansible-galaxy role install")
            for msg in caplog.messages
        )
        assert any(
            msg.startswith("Running ansible-galaxy collection install")
            for msg in caplog.messages
        )


def test__update_env_no_old_value_no_default_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    _update_env("DUMMY_VAR", [])

    assert "DUMMY_VAR" not in os.environ


def test__update_env_no_old_value_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    _update_env("DUMMY_VAR", [], "a:b")

    assert "DUMMY_VAR" not in os.environ


def test__update_env_no_default_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.setenv("DUMMY_VAR", "a:b")

    _update_env("DUMMY_VAR", [])

    assert os.environ["DUMMY_VAR"] == "a:b"


@pytest.mark.parametrize(
    ("value", "result"),
    (
        (["a"], "a"),
        (["a", "b"], "a:b"),
        (["a", "b", "c"], "a:b:c"),
    ),
)
def test__update_env_no_old_value_no_default(
    monkeypatch: MonkeyPatch, value: List[str], result: str
) -> None:
    """Values are concatenated using : as the separator."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    _update_env("DUMMY_VAR", value)

    assert os.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("default", "value", "result"),
    (
        ("a:b", ["c"], "c:a:b"),
        ("a:b", ["c:d"], "c:d:a:b"),
    ),
)
def test__update_env_no_old_value(
    monkeypatch: MonkeyPatch, default: str, value: List[str], result: str
) -> None:
    """Values are appended to default value."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    _update_env("DUMMY_VAR", value, default)

    assert os.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("old_value", "value", "result"),
    (
        ("a:b", ["c"], "c:a:b"),
        ("a:b", ["c:d"], "c:d:a:b"),
    ),
)
def test__update_env_no_default(
    monkeypatch: MonkeyPatch, old_value: str, value: List[str], result: str
) -> None:
    """Values are appended to preexisting value."""
    monkeypatch.setenv("DUMMY_VAR", old_value)

    _update_env("DUMMY_VAR", value)

    assert os.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("old_value", "default", "value", "result"),
    (
        ("", "", ["e"], "e"),
        ("a", "", ["e"], "e:a"),
        ("", "c", ["e"], "e"),
        ("a", "c", ["e:f"], "e:f:a"),
    ),
)
def test__update_env(
    monkeypatch: MonkeyPatch,
    old_value: str,
    default: str,  # pylint: disable=unused-argument
    value: List[str],
    result: str,
) -> None:
    """Defaults are ignored when preexisting value is present."""
    monkeypatch.setenv("DUMMY_VAR", old_value)

    _update_env("DUMMY_VAR", value)

    assert os.environ["DUMMY_VAR"] == result


def test_require_collection_wrong_version(runtime: Runtime) -> None:
    """Tests behaviour of require_collection."""
    subprocess.check_output(
        [
            "ansible-galaxy",
            "collection",
            "install",
            "containers.podman",
            "-p",
            "~/.ansible/collections",
        ]
    )
    with pytest.raises(InvalidPrerequisiteError) as pytest_wrapped_e:
        runtime.require_collection("containers.podman", '9999.9.9')
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC


@pytest.mark.parametrize(
    ("name", "version"),
    (
        ("fake_namespace.fake_name", None),
        ("fake_namespace.fake_name", "9999.9.9"),
    ),
)
def test_require_collection_missing(name: str, version: str, runtime: Runtime) -> None:
    """Tests behaviour of require_collection, missing case."""
    with pytest.raises(AnsibleCompatError) as pytest_wrapped_e:
        runtime.require_collection(name, version)
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC


def test_install_collection(runtime: Runtime) -> None:
    """Check that valid collection installs do not fail."""
    runtime.install_collection("containers.podman:>=1.0")


def test_install_collection_dest(runtime: Runtime, tmp_path: pathlib.Path) -> None:
    """Check that valid collection to custom destination passes."""
    runtime.install_collection("containers.podman:>=1.0", destination=tmp_path)
    expected_file = (
        tmp_path / "ansible_collections" / "containers" / "podman" / "MANIFEST.json"
    )
    assert expected_file.is_file()


def test_install_collection_fail(runtime: Runtime) -> None:
    """Check that invalid collection install fails."""
    with pytest.raises(AnsibleCompatError) as pytest_wrapped_e:
        runtime.install_collection("containers.podman:>=9999.0")
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC
