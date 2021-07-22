# Examples

## Using Ansible runtime

```python
from ansible_compat.runtime import Runtime

def test_runtime():

    # instantiate the runtime using isolated mode, so installing new
    # roles/collections do not pollute the default setup.
    runtime = Runtime(isolated=True)

    # Print Ansible core version
    print(runtime.version)  # 2.9.10 (Version object)
    # Get configuration info from runtime
    print(runtime.config.collections_path)

    # Install a new collection
    runtime.install_collection("containers.podman")

    # Execute a command
    result = runtime.exec(["ansible-doc", "--list"])
```

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
