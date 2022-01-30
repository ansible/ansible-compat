"""Sample usage of AnsibleConfig."""
from ansible_compat.config import AnsibleConfig


def test_example_config() -> None:
    """Test basic functionality of AnsibleConfig."""
    cfg = AnsibleConfig()
    assert isinstance(cfg.ACTION_WARNINGS, bool)
    # you can also use lowercase:
    assert isinstance(cfg.action_warnings, bool)
    # you can also use it as dictionary
    assert cfg["action_warnings"] == cfg.action_warnings
