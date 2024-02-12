"""Sample use of Runtime class."""

from ansible_compat.runtime import Runtime


def test_runtime_example() -> None:
    """Test basic functionality of Runtime class."""
    # instantiate the runtime using isolated mode, so installing new
    # roles/collections do not pollute the default setup.
    runtime = Runtime(isolated=True, max_retries=3)

    # Print Ansible core version
    _ = runtime.version  # 2.9.10 (Version object)
    # Get configuration info from runtime
    _ = runtime.config.collections_path

    # Detect if current project is a collection and install its requirements
    runtime.prepare_environment(install_local=True)  # will retry 3 times if needed

    # Install a new collection (will retry 3 times if needed)
    runtime.install_collection("examples/reqs_v2/community-molecule-0.1.0.tar.gz")

    # Execute a command
    result = runtime.run(["ansible-doc", "--list"])
    assert result.returncode == 0
