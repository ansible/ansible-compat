"""Test the scan path functionality of the runtime."""

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch

from ansible_compat.runtime import Runtime

from .conftest import VirtualEnvironment

V2_COLLECTION_TARBALL = Path("examples/reqs_v2/community-molecule-0.1.0.tar.gz")
V2_COLLECTION_NAMESPACE = "community"
V2_COLLECTION_NAME = "molecule"
V2_COLLECTION_VERSION = "0.1.0"
V2_COLLECTION_FULL_NAME = f"{V2_COLLECTION_NAMESPACE}.{V2_COLLECTION_NAME}"


@pytest.mark.parametrize(
    ("scan", "raises_not_found"),
    (
        pytest.param(False, True, id="disabled"),
        pytest.param(True, False, id="enabled"),
    ),
    ids=str,
)
def test_scan_sys_path(
    venv_module: VirtualEnvironment,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    scan: bool,
    raises_not_found: bool,
) -> None:
    """Confirm sys path is scanned for collections.

    Args:
        venv_module: Fixture for a virtual environment
        monkeypatch: Fixture for monkeypatching
        tmp_path: Fixture for a temporary directory
        scan: Whether to scan the sys path
        raises_not_found: Whether the collection is expected to be found
    """
    # Isolated the test from the others, so ansible will not find collections
    # that might be installed by other tests.
    monkeypatch.setenv("VIRTUAL_ENV", venv_module.project.as_posix())
    monkeypatch.setenv("ANSIBLE_HOME", tmp_path.as_posix())
    # Set the sys scan path environment variable
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_SCAN_SYS_PATH", str(scan))
    # Set the ansible collections paths to avoid bleed from other tests
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", str(tmp_path))

    runtime_tmp = Runtime(project_dir=tmp_path, isolated=True)
    first_site_package_dir = venv_module.site_package_dirs()[0]

    installed_to = (
        first_site_package_dir
        / "ansible_collections"
        / V2_COLLECTION_NAMESPACE
        / V2_COLLECTION_NAME
    )
    if not installed_to.exists():
        # Install the collection into the venv site packages directory, force
        # as of yet this test is not isolated from the rest of the system
        runtime_tmp.install_collection(
            collection=V2_COLLECTION_TARBALL,
            destination=first_site_package_dir,
            force=True,
        )
    # Confirm the collection is installed
    assert installed_to.exists()

    script = textwrap.dedent(
        f"""
    import json;
    from ansible_compat.runtime import Runtime;
    r = Runtime();
    fv, cp = r.require_collection(name="{V2_COLLECTION_FULL_NAME}", version="{V2_COLLECTION_VERSION}", install=False);
    print(json.dumps({{"found_version": str(fv), "collection_path": str(cp)}}));
    """,
    )

    proc = venv_module.python_script_run(script)
    if raises_not_found:
        assert proc.returncode != 0, (proc.stdout, proc.stderr)
        assert "InvalidPrerequisiteError" in proc.stderr
        assert "'community.molecule' not found" in proc.stderr
    else:
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        result = json.loads(proc.stdout)
        assert result["found_version"] == V2_COLLECTION_VERSION
        assert result["collection_path"] == str(installed_to)

    runtime_tmp.clean()


def test_ro_venv() -> None:
    """Tests behavior when the virtual environment is read-only.

    See Related https://github.com/ansible/ansible-compat/pull/470
    """
    tox_work_dir = os.environ.get("TOX_WORK_DIR", ".tox")
    venv_path = f"{tox_work_dir}/ro"
    commands = [
        f"mkdir -p {venv_path}",
        f"chmod -R a+w {venv_path}",
        f"python -m venv --symlinks {venv_path}",
        f"{venv_path}/bin/python -m pip install -q -e .",
        f"chmod -R a-w {venv_path}",
        f"{venv_path}/bin/python -c \"from ansible_compat.runtime import Runtime; r = Runtime(); r.install_collection('ansible.posix:>=2.0.0')\"",
    ]
    for cmd in commands:
        result = subprocess.run(  # noqa: S602
            cmd,
            check=False,
            shell=True,
            text=True,
            capture_output=True,
        )
        assert (
            result.returncode == 0
        ), f"Got {result.returncode} running {cmd}\n\tstderr: {result.stderr}\n\tstdout: {result.stdout}"
