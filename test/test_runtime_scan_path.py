"""Test the scan path functionality of the runtime."""

import json
import textwrap
from dataclasses import dataclass, fields
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


@dataclass
class ScanSysPath:
    """Parameters for scan tests."""

    scan: bool
    raises_not_found: bool

    def __str__(self) -> str:
        """Return a string representation of the object."""
        parts = [
            f"{field.name}{str(getattr(self, field.name))[0]}" for field in fields(self)
        ]
        return "-".join(parts)


@pytest.mark.parametrize(
    ("param"),
    (
        ScanSysPath(scan=False, raises_not_found=True),
        ScanSysPath(scan=True, raises_not_found=False),
    ),
    ids=str,
)
def test_scan_sys_path(
    venv_module: VirtualEnvironment,
    monkeypatch: MonkeyPatch,
    runtime_tmp: Runtime,
    tmp_path: Path,
    param: ScanSysPath,
) -> None:
    """Confirm sys path is scanned for collections.

    :param venv_module: Fixture for a virtual environment
    :param monkeypatch: Fixture for monkeypatching
    :param runtime_tmp: Fixture for a Runtime object
    :param tmp_dir: Fixture for a temporary directory
    :param param: The parameters for the test
    """
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
    # Set the sys scan path environment variable
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_SCAN_SYS_PATH", str(param.scan))
    # Set the ansible collections paths to avoid bleed from other tests
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", str(tmp_path))

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
    if param.raises_not_found:
        assert proc.returncode != 0, (proc.stdout, proc.stderr)
        assert "InvalidPrerequisiteError" in proc.stderr
        assert "'community.molecule' not found" in proc.stderr
    else:
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        result = json.loads(proc.stdout)
        assert result["found_version"] == V2_COLLECTION_VERSION
        assert result["collection_path"] == str(installed_to)
