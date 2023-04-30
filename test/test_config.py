"""Tests for ansible_compat.config submodule."""
import copy
import subprocess

import pytest
from _pytest.monkeypatch import MonkeyPatch
from packaging.version import Version

from ansible_compat.config import AnsibleConfig, ansible_version, parse_ansible_version
from ansible_compat.errors import InvalidPrerequisiteError, MissingAnsibleError


def test_config() -> None:
    """Checks that config vars are loaded with their expected type."""
    config = AnsibleConfig()
    assert isinstance(config.ACTION_WARNINGS, bool)
    assert isinstance(config.CACHE_PLUGIN_PREFIX, str)
    assert isinstance(config.CONNECTION_FACTS_MODULES, dict)
    assert config.ANSIBLE_COW_PATH is None
    assert isinstance(config.NETWORK_GROUP_MODULES, list)
    assert isinstance(config.DEFAULT_GATHER_TIMEOUT, (int, type(None)))

    # check lowercase and older name aliasing
    assert isinstance(config.collections_paths, list)
    assert isinstance(config.collections_path, list)
    assert config.collections_paths == config.collections_path

    # check if we can access the special data member
    assert config.data["ACTION_WARNINGS"] == config.ACTION_WARNINGS

    with pytest.raises(AttributeError):
        _ = config.THIS_DOES_NOT_EXIST


def test_config_with_dump() -> None:
    """Tests that config can parse given dumps."""
    config = AnsibleConfig(config_dump="ACTION_WARNINGS(default) = True")
    assert config.ACTION_WARNINGS is True


def test_config_copy() -> None:
    """Checks ability to use copy/deepcopy."""
    config = AnsibleConfig()
    new_config = copy.copy(config)
    assert isinstance(new_config, AnsibleConfig)
    assert new_config is not config
    # deepcopy testing
    new_config = copy.deepcopy(config)
    assert isinstance(new_config, AnsibleConfig)
    assert new_config is not config


def test_parse_ansible_version_fail() -> None:
    """Checks that parse_ansible_version raises an error on invalid input."""
    with pytest.raises(
        InvalidPrerequisiteError,
        match="Unable to parse ansible cli version",
    ):
        parse_ansible_version("foo")


def test_ansible_version_missing(monkeypatch: MonkeyPatch) -> None:
    """Validate ansible_version behavior when ansible is missing."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(  # noqa: ARG005
            args=[],
            returncode=1,
        ),
    )
    with pytest.raises(
        MissingAnsibleError,
        match="Unable to find a working copy of ansible executable.",
    ):
        # bypassing lru cache
        ansible_version.__wrapped__()


def test_ansible_version() -> None:
    """Validate ansible_version behavior."""
    assert ansible_version() >= Version("1.0")


def test_ansible_version_arg() -> None:
    """Validate ansible_version behavior."""
    assert ansible_version("2.0") >= Version("1.0")
