# ansible-compat

A python package contains functions that facilitates working with various
versions of Ansible, 2.9 and newer.

## Access to Ansible configuration

As you may not want to parse `ansible-config dump` yourself, you
can make use of a simple python class that facilitates access to
it, using python data types.

```python
from ansible_compat.config import AnsibleConfig


def test_example_config():
    cfg = AnsibleConfig()
    assert isinstance(cfg.ACTION_WARNINGS, bool)
    # you can also use lowercase:
    assert isinstance(cfg.action_warnings, bool)
    # you can also use it as dictionary
    assert cfg['action_warnings'] == cfg.action_warnings
```
