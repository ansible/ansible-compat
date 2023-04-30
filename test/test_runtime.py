"""Tests for Runtime class."""
# pylint: disable=protected-access
import logging
import os
import pathlib
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from typing import Any, Union

import pytest
from _pytest.monkeypatch import MonkeyPatch
from packaging.version import Version
from pytest_mock import MockerFixture

from ansible_compat.constants import INVALID_PREREQUISITES_RC
from ansible_compat.errors import (
    AnsibleCommandError,
    AnsibleCompatError,
    InvalidPrerequisiteError,
)
from ansible_compat.runtime import CompletedProcess, Runtime


def test_runtime_version(runtime: Runtime) -> None:
    """Tests version property."""
    version = runtime.version
    assert isinstance(version, Version)
    # tests that caching property value worked (coverage)
    assert version == runtime.version


@pytest.mark.parametrize(
    "require_module",
    (True, False),
    ids=("module-required", "module-unrequired"),
)
def test_runtime_version_outdated(require_module: bool) -> None:
    """Checks that instantiation raises if version is outdated."""
    with pytest.raises(RuntimeError, match="Found incompatible version of ansible"):
        Runtime(min_required_version="9999.9.9", require_module=require_module)


def test_runtime_missing_ansible_module(monkeypatch: MonkeyPatch) -> None:
    """Checks that we produce a RuntimeError when ansible module is missing."""

    class RaiseException:
        """Class to raise an exception."""

        def __init__(
            self,
            *args: Any,  # noqa: ARG002,ANN401
            **kwargs: Any,  # noqa: ARG002,ANN401
        ) -> None:
            raise ModuleNotFoundError

    monkeypatch.setattr("importlib.import_module", RaiseException)

    with pytest.raises(RuntimeError, match="Unable to find Ansible python module."):
        Runtime(require_module=True)


def test_runtime_mismatch_ansible_module(monkeypatch: MonkeyPatch) -> None:
    """Test that missing module is detected."""
    monkeypatch.setattr("ansible.release.__version__", "0.0.0", raising=False)
    with pytest.raises(RuntimeError, match="versions do not match"):
        Runtime(require_module=True)


def test_runtime_require_module() -> None:
    """Check that require_module successful pass."""
    Runtime(require_module=True)
    # Now we try to set the collection path, something to check if that is
    # causing an exception, as 2.15 introduced new init code.
    from ansible.utils.collection_loader import (  # pylint: disable=import-outside-toplevel
        AnsibleCollectionConfig,
    )

    AnsibleCollectionConfig.playbook_paths = "."
    # Calling it again in order to see that it does not produce UserWarning: AnsibleCollectionFinder has already been configured
    # which is done by Ansible core 2.15+. We added special code inside Runtime
    # that should avoid initializing twice and raise that warning.
    Runtime(require_module=True)


def test_runtime_version_fail_module(mocker: MockerFixture) -> None:
    """Tests for failure to detect Ansible version."""
    patched = mocker.patch(
        "ansible_compat.runtime.parse_ansible_version",
        autospec=True,
    )
    patched.side_effect = InvalidPrerequisiteError(
        "Unable to parse ansible cli version",
    )
    runtime = Runtime()
    with pytest.raises(
        InvalidPrerequisiteError,
        match="Unable to parse ansible cli version",
    ):
        _ = runtime.version  # pylint: disable=pointless-statement


def test_runtime_version_fail_cli(mocker: MockerFixture) -> None:
    """Tests for failure to detect Ansible version."""
    mocker.patch(
        "ansible_compat.runtime.Runtime.run",
        return_value=CompletedProcess(
            ["x"],
            returncode=123,
            stdout="oops",
            stderr="some error",
        ),
        autospec=True,
    )
    runtime = Runtime()
    with pytest.raises(
        RuntimeError,
        match="Unable to find a working copy of ansible executable.",
    ):
        _ = runtime.version  # pylint: disable=pointless-statement


def test_runtime_prepare_ansible_paths_validation() -> None:
    """Check that we validate collection_path."""
    runtime = Runtime()
    runtime.config.collections_paths = "invalid-value"  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="Unexpected ansible configuration"):
        runtime._prepare_ansible_paths()


@pytest.mark.parametrize(
    ("folder", "role_name", "isolated"),
    (
        ("ansible-role-sample", "acme.sample", True),
        ("acme.sample2", "acme.sample2", True),
        ("sample3", "acme.sample3", True),
        ("sample4", "acme.sample4", False),
    ),
    ids=("1", "2", "3", "4"),
)
def test_runtime_install_role(
    caplog: pytest.LogCaptureFixture,
    folder: str,
    role_name: str,
    isolated: bool,
) -> None:
    """Checks that we can install roles."""
    caplog.set_level(logging.INFO)
    project_dir = Path(__file__).parent / "roles" / folder
    runtime = Runtime(isolated=isolated, project_dir=project_dir)
    runtime.prepare_environment(install_local=True)
    # check that role appears as installed now
    result = runtime.run(["ansible-galaxy", "list"])
    assert result.returncode == 0, result
    assert role_name in result.stdout
    if isolated:
        assert pathlib.Path(f"{runtime.cache_dir}/roles/{role_name}").is_symlink()
    else:
        assert pathlib.Path(
            f"{Path(runtime.config.default_roles_path[0]).expanduser()}/{role_name}",
        ).is_symlink()
    runtime.clean()
    # also test that clean does not break when cache_dir is missing
    tmp_dir = runtime.cache_dir
    runtime.cache_dir = None
    runtime.clean()
    runtime.cache_dir = tmp_dir


def test_prepare_environment_with_collections(tmp_path: pathlib.Path) -> None:
    """Check that collections are correctly installed."""
    runtime = Runtime(isolated=True, project_dir=tmp_path)
    runtime.prepare_environment(required_collections={"community.molecule": "0.1.0"})


def test_runtime_install_requirements_missing_file() -> None:
    """Check that missing requirements file is ignored."""
    # Do not rely on this behavior, it may be removed in the future
    runtime = Runtime()
    runtime.install_requirements(Path("/that/does/not/exist"))


@pytest.mark.parametrize(
    ("file", "exc", "msg"),
    (
        (
            Path("/dev/null"),
            InvalidPrerequisiteError,
            "file is not a valid Ansible requirements file",
        ),
        (
            Path(__file__).parent / "assets" / "requirements-invalid-collection.yml",
            AnsibleCommandError,
            "Got 1 exit code while running: ansible-galaxy",
        ),
        (
            Path(__file__).parent / "assets" / "requirements-invalid-role.yml",
            AnsibleCommandError,
            "Got 1 exit code while running: ansible-galaxy",
        ),
    ),
    ids=("empty", "invalid-collection", "invalid-role"),
)
def test_runtime_install_requirements_invalid_file(
    file: Path,
    exc: type[Any],
    msg: str,
) -> None:
    """Check that invalid requirements file is raising."""
    runtime = Runtime()
    with pytest.raises(
        exc,
        match=msg,
    ):
        runtime.install_requirements(file)


@contextmanager
def cwd(path: Path) -> Iterator[None]:
    """Context manager for temporary changing current working directory."""
    old_pwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_pwd)


def test_prerun_reqs_v1(caplog: pytest.LogCaptureFixture, runtime: Runtime) -> None:
    """Checks that the linter can auto-install requirements v1 when found."""
    path = Path(__file__).parent.parent / "examples" / "reqs_v1"
    with cwd(path), caplog.at_level(logging.INFO):
        runtime.prepare_environment()
    assert any(
        msg.startswith("Running ansible-galaxy role install") for msg in caplog.messages
    )
    assert all(
        "Running ansible-galaxy collection install" not in msg
        for msg in caplog.messages
    )


def test_prerun_reqs_v2(caplog: pytest.LogCaptureFixture, runtime: Runtime) -> None:
    """Checks that the linter can auto-install requirements v2 when found."""
    path = (Path(__file__).parent.parent / "examples" / "reqs_v2").resolve()
    with cwd(path):
        with caplog.at_level(logging.INFO):
            runtime.prepare_environment()
        assert any(
            msg.startswith("Running ansible-galaxy role install")
            for msg in caplog.messages
        )
        assert any(
            msg.startswith("Running ansible-galaxy collection install")
            for msg in caplog.messages
        )


def test__update_env_no_old_value_no_default_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", [])

    assert "DUMMY_VAR" not in runtime.environ


def test__update_env_no_old_value_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", [], "a:b")

    assert "DUMMY_VAR" not in runtime.environ


def test__update_env_no_default_no_value(monkeypatch: MonkeyPatch) -> None:
    """Make sure empty value does not touch environment."""
    monkeypatch.setenv("DUMMY_VAR", "a:b")

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", [])

    assert runtime.environ["DUMMY_VAR"] == "a:b"


@pytest.mark.parametrize(
    ("value", "result"),
    (
        (["a"], "a"),
        (["a", "b"], "a:b"),
        (["a", "b", "c"], "a:b:c"),
    ),
)
def test__update_env_no_old_value_no_default(
    monkeypatch: MonkeyPatch,
    value: list[str],
    result: str,
) -> None:
    """Values are concatenated using : as the separator."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", value)

    assert runtime.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("default", "value", "result"),
    (
        ("a:b", ["c"], "c:a:b"),
        ("a:b", ["c:d"], "c:d:a:b"),
    ),
)
def test__update_env_no_old_value(
    monkeypatch: MonkeyPatch,
    default: str,
    value: list[str],
    result: str,
) -> None:
    """Values are appended to default value."""
    monkeypatch.delenv("DUMMY_VAR", raising=False)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", value, default)

    assert runtime.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("old_value", "value", "result"),
    (
        ("a:b", ["c"], "c:a:b"),
        ("a:b", ["c:d"], "c:d:a:b"),
    ),
)
def test__update_env_no_default(
    monkeypatch: MonkeyPatch,
    old_value: str,
    value: list[str],
    result: str,
) -> None:
    """Values are appended to preexisting value."""
    monkeypatch.setenv("DUMMY_VAR", old_value)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", value)

    assert runtime.environ["DUMMY_VAR"] == result


@pytest.mark.parametrize(
    ("old_value", "default", "value", "result"),
    (
        ("", "", ["e"], "e"),
        ("a", "", ["e"], "e:a"),
        ("", "c", ["e"], "e"),
        ("a", "c", ["e:f"], "e:f:a"),
    ),
)
def test__update_env(
    monkeypatch: MonkeyPatch,
    old_value: str,
    default: str,  # pylint: disable=unused-argument # noqa: ARG001
    value: list[str],
    result: str,
) -> None:
    """Defaults are ignored when preexisting value is present."""
    monkeypatch.setenv("DUMMY_VAR", old_value)

    runtime = Runtime()
    runtime._update_env("DUMMY_VAR", value)

    assert runtime.environ["DUMMY_VAR"] == result


def test_require_collection_wrong_version(runtime: Runtime) -> None:
    """Tests behaviour of require_collection."""
    subprocess.check_output(
        [  # noqa: S603
            "ansible-galaxy",
            "collection",
            "install",
            "examples/reqs_v2/community-molecule-0.1.0.tar.gz",
            "-p",
            "~/.ansible/collections",
        ],
    )
    with pytest.raises(InvalidPrerequisiteError) as pytest_wrapped_e:
        runtime.require_collection("community.molecule", "9999.9.9")
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC


def test_require_collection_invalid_name(runtime: Runtime) -> None:
    """Check that require_collection raise with invalid collection name."""
    with pytest.raises(
        InvalidPrerequisiteError,
        match="Invalid collection name supplied:",
    ):
        runtime.require_collection("that-is-invalid")


def test_require_collection_invalid_collections_path(runtime: Runtime) -> None:
    """Check that require_collection raise with invalid collections path."""
    runtime.config.collections_paths = "/that/is/invalid"  # type: ignore[assignment]
    with pytest.raises(
        InvalidPrerequisiteError,
        match="Unable to determine ansible collection paths",
    ):
        runtime.require_collection("community.molecule")


def test_require_collection_preexisting_broken(tmp_path: pathlib.Path) -> None:
    """Check that require_collection raise with broken pre-existing collection."""
    runtime = Runtime(isolated=True, project_dir=tmp_path)
    dest_path: str = runtime.config.collections_paths[0]
    dest = pathlib.Path(dest_path) / "ansible_collections" / "foo" / "bar"
    dest.mkdir(parents=True, exist_ok=True)
    with pytest.raises(InvalidPrerequisiteError, match="missing MANIFEST.json"):
        runtime.require_collection("foo.bar")


def test_require_collection(runtime_tmp: Runtime) -> None:
    """Check that require collection successful install case."""
    runtime_tmp.require_collection("community.molecule", "0.1.0")


@pytest.mark.parametrize(
    ("name", "version", "install"),
    (
        ("fake_namespace.fake_name", None, True),
        ("fake_namespace.fake_name", "9999.9.9", True),
        ("fake_namespace.fake_name", None, False),
    ),
    ids=("a", "b", "c"),
)
def test_require_collection_missing(
    name: str,
    version: str,
    install: bool,
    runtime: Runtime,
) -> None:
    """Tests behaviour of require_collection, missing case."""
    with pytest.raises(AnsibleCompatError) as pytest_wrapped_e:
        runtime.require_collection(name=name, version=version, install=install)
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC


def test_install_collection(runtime: Runtime) -> None:
    """Check that valid collection installs do not fail."""
    runtime.install_collection("examples/reqs_v2/community-molecule-0.1.0.tar.gz")


def test_install_collection_dest(runtime: Runtime, tmp_path: pathlib.Path) -> None:
    """Check that valid collection to custom destination passes."""
    runtime.install_collection(
        "examples/reqs_v2/community-molecule-0.1.0.tar.gz",
        destination=tmp_path,
    )
    expected_file = (
        tmp_path / "ansible_collections" / "community" / "molecule" / "MANIFEST.json"
    )
    assert expected_file.is_file()


def test_install_collection_fail(runtime: Runtime) -> None:
    """Check that invalid collection install fails."""
    with pytest.raises(AnsibleCompatError) as pytest_wrapped_e:
        runtime.install_collection("community.molecule:>=9999.0")
    assert pytest_wrapped_e.type == InvalidPrerequisiteError
    assert pytest_wrapped_e.value.code == INVALID_PREREQUISITES_RC


def test_install_galaxy_role(runtime_tmp: Runtime) -> None:
    """Check install role with empty galaxy file."""
    pathlib.Path(f"{runtime_tmp.project_dir}/galaxy.yml").touch()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").touch()
    # this should only raise a warning
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=1)
    # this should test the bypass role name check path
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=2)
    # this should raise an error
    with pytest.raises(
        InvalidPrerequisiteError,
        match="does not follow current galaxy requirements",
    ):
        runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=0)


def test_install_galaxy_role_unlink(
    runtime_tmp: Runtime,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test ability to unlink incorrect symlinked roles."""
    caplog.set_level(logging.INFO)
    runtime_tmp.prepare_environment()
    pathlib.Path(f"{runtime_tmp.cache_dir}/roles").mkdir(parents=True, exist_ok=True)
    pathlib.Path(f"{runtime_tmp.cache_dir}/roles/acme.get_rich").symlink_to("/dev/null")
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").write_text(
        """galaxy_info:
  role_name: get_rich
  namespace: acme
""",
        encoding="utf-8",
    )
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir)
    assert "symlink to current repository" in caplog.text


def test_install_galaxy_role_bad_namespace(runtime_tmp: Runtime) -> None:
    """Check install role with bad namespace in galaxy info."""
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").write_text(
        """galaxy_info:
  role_name: foo
  author: bar
  namespace: ["xxx"]
""",
    )
    # this should raise an error regardless the role_name_check value
    with pytest.raises(AnsibleCompatError, match="Role namespace must be string, not"):
        runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=1)


@pytest.mark.parametrize(
    "galaxy_info",
    (
        """galaxy_info:
  role_name: foo-bar
  namespace: acme
""",
        """galaxy_info:
  role_name: foo-bar
""",
    ),
    ids=("bad-name", "bad-name-without-namespace"),
)
def test_install_galaxy_role_name_role_name_check_equals_to_1(
    runtime_tmp: Runtime,
    galaxy_info: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Check install role with bad role name in galaxy info."""
    caplog.set_level(logging.WARN)
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").write_text(
        galaxy_info,
        encoding="utf-8",
    )

    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=1)
    assert "Computed fully qualified role name of " in caplog.text


def test_install_galaxy_role_no_checks(runtime_tmp: Runtime) -> None:
    """Check install role with bad namespace in galaxy info."""
    runtime_tmp.prepare_environment()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir()
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").write_text(
        """galaxy_info:
  role_name: foo
  author: bar
  namespace: acme
""",
    )
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, role_name_check=2)
    result = runtime_tmp.run(["ansible-galaxy", "list"])
    assert "- acme.foo," in result.stdout
    assert result.returncode == 0, result


def test_upgrade_collection(runtime_tmp: Runtime) -> None:
    """Check that collection upgrade is possible."""
    # ensure that we inject our tmp folders in ansible paths
    runtime_tmp.prepare_environment()

    # we install specific oudated version of a collection
    runtime_tmp.install_collection("examples/reqs_v2/community-molecule-0.1.0.tar.gz")
    with pytest.raises(
        InvalidPrerequisiteError,
        match="Found community.molecule collection 0.1.0 but 9.9.9 or newer is required.",
    ):
        # we check that when install=False, we raise error
        runtime_tmp.require_collection("community.molecule", "9.9.9", install=False)
    # this should not fail, as we have this version
    runtime_tmp.require_collection("community.molecule", "0.1.0")


def test_require_collection_no_cache_dir() -> None:
    """Check require_collection without a cache directory."""
    runtime = Runtime()
    assert not runtime.cache_dir
    runtime.require_collection("community.molecule", "0.1.0", install=True)


def test_runtime_env_ansible_library(monkeypatch: MonkeyPatch) -> None:
    """Verify that custom path specified using ANSIBLE_LIBRARY is not lost."""
    path_name = "foo"
    monkeypatch.setenv("ANSIBLE_LIBRARY", path_name)

    path_name = os.path.realpath(path_name)
    runtime = Runtime()
    runtime.prepare_environment()
    assert path_name in runtime.config.default_module_path


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    (
        ("1.0", "9999.0", True),
        (None, "9999.0", True),
        ("1.0", None, True),
        ("9999.0", None, False),
        (None, "1.0", False),
    ),
    ids=("1", "2", "3", "4", "5"),
)
def test_runtime_version_in_range(
    lower: Union[str, None],
    upper: Union[str, None],
    expected: bool,
) -> None:
    """Validate functioning of version_in_range."""
    runtime = Runtime()
    assert runtime.version_in_range(lower=lower, upper=upper) is expected


@pytest.mark.parametrize(
    ("path", "scenario"),
    (
        ("test/collections/acme.goodies", "default"),
        ("test/collections/acme.goodies/roles/baz", "deep_scenario"),
    ),
    ids=("normal", "deep"),
)
def test_install_collection_from_disk(path: str, scenario: str) -> None:
    """Tests ability to install a local collection."""
    # ensure we do not have acme.google installed in user directory as it may
    # produce false positives
    rmtree(
        pathlib.Path(
            "~/.ansible/collections/ansible_collections/acme/goodies",
        ).expanduser(),
        ignore_errors=True,
    )
    with cwd(Path(path)):
        runtime = Runtime(isolated=True)
        # this should call install_collection_from_disk(".")
        runtime.prepare_environment(install_local=True)
        # that molecule converge playbook can be used without molecule and
        # should validate that the installed collection is available.
        result = runtime.run(["ansible-playbook", f"molecule/{scenario}/converge.yml"])
        assert result.returncode == 0, result.stdout
        runtime.clean()


def test_install_collection_from_disk_fail() -> None:
    """Tests that we fail to install a broken collection."""
    with cwd(Path("test/collections/acme.broken")):
        runtime = Runtime(isolated=True)
        with pytest.raises(RuntimeError) as exc_info:
            runtime.prepare_environment(install_local=True)
        # based on version of Ansible used, we might get a different error,
        # but both errors should be considered acceptable
        assert exc_info.type in (
            RuntimeError,
            AnsibleCompatError,
            AnsibleCommandError,
            InvalidPrerequisiteError,
        )
        assert exc_info.match(
            "(is missing the following mandatory|Got 1 exit code while running: ansible-galaxy collection build)",
        )


def test_prepare_environment_offline_role() -> None:
    """Ensure that we can make use of offline roles."""
    with cwd(Path("test/roles/acme.missing_deps")):
        runtime = Runtime(isolated=True)
        runtime.prepare_environment(install_local=True, offline=True)


def test_runtime_run(runtime: Runtime) -> None:
    """Check if tee and non tee mode return same kind of results."""
    result1 = runtime.run(["seq", "10"])
    result2 = runtime.run(["seq", "10"], tee=True)
    assert result1.returncode == result2.returncode
    assert result1.stderr == result2.stderr
    assert result1.stdout == result2.stdout


def test_runtime_exec_cwd(runtime: Runtime) -> None:
    """Check if passing cwd works as expected."""
    path = Path("/")
    result1 = runtime.run(["pwd"], cwd=path)
    result2 = runtime.run(["pwd"])
    assert result1.stdout.rstrip() == str(path)
    assert result1.stdout != result2.stdout


def test_runtime_exec_env(runtime: Runtime) -> None:
    """Check if passing env works."""
    result = runtime.run(["printenv", "FOO"])
    assert not result.stdout

    result = runtime.run(["printenv", "FOO"], env={"FOO": "bar"})
    assert result.stdout.rstrip() == "bar"

    runtime.environ["FOO"] = "bar"
    result = runtime.run(["printenv", "FOO"])
    assert result.stdout.rstrip() == "bar"
