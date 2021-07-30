"""Sample use of Runtime class."""
from ansible_compat.runtime import Runtime


def test_runtime() -> None:
    """Test basic functionality of Runtime class."""
    # instantiate the runtime using isolated mode, so installing new
    # roles/collections do not pollute the default setup.
    runtime = Runtime(isolated=True, max_retries=3)

    # Print Ansible core version
    print(runtime.version)  # 2.9.10 (Version object)
    # Get configuration info from runtime
    print(runtime.config.collections_path)

    # Detect if current project is a collection and install its requirements
    runtime.prepare_environment()  # will retry 3 times if needed

    # Install a new collection (will retry 3 times if needed)
    runtime.install_collection("containers.podman")

    # Execute a command
    result = runtime.exec(["ansible-doc", "--list"])
    assert result.returncode == 0
