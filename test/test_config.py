"""Tests for ansible_compat.config submodule."""
import copy

import pytest
from _pytest.monkeypatch import MonkeyPatch
from packaging.version import Version

from ansible_compat.config import AnsibleConfig, ansible_collections_path


def test_config() -> None:
    """Checks that config vars are loaded with their expected type."""
    config = AnsibleConfig()
    assert isinstance(config.ACTION_WARNINGS, bool)
    assert isinstance(config.CACHE_PLUGIN_PREFIX, str)
    assert isinstance(config.CONNECTION_FACTS_MODULES, dict)
    assert config.ANSIBLE_COW_PATH is None
    assert isinstance(config.NETWORK_GROUP_MODULES, list)
    assert isinstance(config.DEFAULT_GATHER_TIMEOUT, int)

    # check lowercase and older name aliasing
    assert isinstance(config.collections_paths, list)
    assert isinstance(config.collections_path, list)

    with pytest.raises(AttributeError):
        print(config.THIS_DOES_NOT_EXIST)


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


def test_ansible_collections_path_210(monkeypatch: MonkeyPatch) -> None:
    """Checks that ansible_collections_path works as expected correctly."""
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATHS", "foo")
    monkeypatch.delenv("ANSIBLE_COLLECTIONS_PATH", False)
    assert ansible_collections_path() == "ANSIBLE_COLLECTIONS_PATHS"
    monkeypatch.delenv("ANSIBLE_COLLECTIONS_PATHS", False)
    monkeypatch.setattr(
        "ansible_compat.config.ansible_version", lambda x="2.10.0": Version(x)
    )
    assert ansible_collections_path() == "ANSIBLE_COLLECTIONS_PATH"


def test_ansible_collections_path_29(monkeypatch: MonkeyPatch) -> None:
    """Checks that ansible_collections_path works as expected correctly."""
    monkeypatch.delenv("ANSIBLE_COLLECTIONS_PATHS", False)
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", "foo")
    assert ansible_collections_path() == "ANSIBLE_COLLECTIONS_PATH"
    monkeypatch.delenv("ANSIBLE_COLLECTIONS_PATH", False)
    monkeypatch.setattr(
        "ansible_compat.config.ansible_version", lambda x="2.9.0": Version(x)
    )
    assert ansible_collections_path() == "ANSIBLE_COLLECTIONS_PATHS"
