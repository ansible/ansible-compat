"""Sample use of Runtime class."""
from ansible_compat.runtime import Runtime


def test_runtime() -> None:
    """Test basic functionality of Runtime class."""
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
    assert result.returncode == 0
