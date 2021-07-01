"""Tests for ansible_compat.config submodule."""
import copy

import pytest

import ansible_compat


def test_config() -> None:
    """Checks that config vars are loaded with their expected type."""
    config = ansible_compat.config.AnsibleConfig()
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
    config = ansible_compat.config.AnsibleConfig()
    new_config = copy.copy(config)
    assert isinstance(new_config, ansible_compat.config.AnsibleConfig)
    assert new_config is not config
    # deepcopy testing
    new_config = copy.deepcopy(config)
    assert isinstance(new_config, ansible_compat.config.AnsibleConfig)
    assert new_config is not config
