"""Tests for Runtime class."""

# pylint: disable=protected-access,too-many-lines
from __future__ import annotations

import logging
import os
import pathlib
import subprocess
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Any

import pytest
from ansible.plugins.loader import module_loader
from packaging.version import Version

from ansible_compat.constants import INVALID_PREREQUISITES_RC
from ansible_compat.errors import (
    AnsibleCommandError,
    AnsibleCompatError,
    InvalidPrerequisiteError,
)
from ansible_compat.runtime import (
    CompletedProcess,
    Runtime,
    _get_galaxy_role_name,
    is_url,
    search_galaxy_paths,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock import MockerFixture


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


def test_prepare_environment_with_collections(runtime_tmp: Runtime) -> None:
    """Check that collections are correctly installed."""
    runtime_tmp.prepare_environment(
        required_collections={"community.molecule": "0.1.0"},
        install_local=True,
    )
    assert "community.molecule" in runtime_tmp.collections


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


def test_prerun_reqs_v1(caplog: pytest.LogCaptureFixture) -> None:
    """Checks that the linter can auto-install requirements v1 when found."""
    path = Path(__file__).parent.parent / "examples" / "reqs_v1"
    runtime = Runtime(project_dir=path, verbosity=1)
    with cwd(path):
        runtime.prepare_environment()
    assert any(
        msg.startswith("Running ansible-galaxy role install") for msg in caplog.messages
    )
    assert all(
        "Running ansible-galaxy collection install" not in msg
        for msg in caplog.messages
    )


def test_prerun_reqs_v2(caplog: pytest.LogCaptureFixture) -> None:
    """Checks that the linter can auto-install requirements v2 when found."""
    path = (Path(__file__).parent.parent / "examples" / "reqs_v2").resolve()
    runtime = Runtime(project_dir=path, verbosity=1)
    with cwd(path):
        runtime.prepare_environment()
        assert any(
            msg.startswith("Running ansible-galaxy role install")
            for msg in caplog.messages
        )
        assert any(
            msg.startswith("Running ansible-galaxy collection install")
            for msg in caplog.messages
        )


def test_prerun_reqs_broken() -> None:
    """Checks that the we report invalid requirements.yml file."""
    path = (Path(__file__).parent.parent / "examples" / "reqs_broken").resolve()
    runtime = Runtime(project_dir=path, verbosity=1)
    with cwd(path), pytest.raises(InvalidPrerequisiteError):
        runtime.prepare_environment()


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
    subprocess.check_output(  # noqa: S603
        [
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


def test_require_collection_preexisting_broken(runtime_tmp: Runtime) -> None:
    """Check that require_collection raise with broken pre-existing collection."""
    dest_path: str = runtime_tmp.config.collections_paths[0]
    dest = pathlib.Path(dest_path) / "ansible_collections" / "foo" / "bar"
    dest.mkdir(parents=True, exist_ok=True)
    with pytest.raises(InvalidPrerequisiteError, match="missing MANIFEST.json"):
        runtime_tmp.require_collection("foo.bar")


def test_require_collection_install(runtime_tmp: Runtime) -> None:
    """Check that require collection successful install case, including upgrade path."""
    runtime_tmp.install_collection("ansible.posix:==1.5.2")
    runtime_tmp.load_collections()
    collection = runtime_tmp.collections["ansible.posix"]
    assert collection.version == "1.5.2"
    runtime_tmp.require_collection(name="ansible.posix", version="1.5.4", install=True)
    runtime_tmp.load_collections()
    collection = runtime_tmp.collections["ansible.posix"]
    assert Version(collection.version) >= Version("1.5.4")


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


def test_install_collection_git(runtime: Runtime) -> None:
    """Check that valid collection installs do not fail."""
    runtime.install_collection(
        "git+https://github.com/ansible-collections/ansible.posix,main",
    )


def test_install_collection_dest(runtime: Runtime, tmp_path: pathlib.Path) -> None:
    """Check that valid collection to custom destination passes."""
    # Since Ansible 2.15.3 there is no guarantee that this will install the collection at requested path
    # as it might decide to not install anything if requirement is already present at another location.
    runtime.install_collection(
        "examples/reqs_v2/community-molecule-0.1.0.tar.gz",
        destination=tmp_path,
    )
    runtime.load_collections()
    for collection in runtime.collections:
        if collection == "community.molecule":
            return
    msg = "Failed to find collection as installed."
    raise AssertionError(msg)


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
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test ability to unlink incorrect symlinked roles."""
    runtime_tmp = Runtime(verbosity=1, isolated=True)
    runtime_tmp.prepare_environment()
    assert runtime_tmp.cache_dir is not None
    pathlib.Path(f"{runtime_tmp.cache_dir}/roles").mkdir(parents=True, exist_ok=True)
    roledir = pathlib.Path(f"{runtime_tmp.cache_dir}/roles/acme.get_rich")
    if not roledir.exists():
        roledir.symlink_to("/dev/null")
    pathlib.Path(f"{runtime_tmp.project_dir}/meta").mkdir(exist_ok=True)
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").write_text(
        """galaxy_info:
  role_name: get_rich
  namespace: acme
""",
        encoding="utf-8",
    )
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir)
    assert "symlink to current repository" in caplog.text
    pathlib.Path(f"{runtime_tmp.project_dir}/meta/main.yml").unlink()


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


def test_install_galaxy_role_no_meta(runtime_tmp: Runtime) -> None:
    """Check install role with missing meta/main.yml."""
    # This should fail because meta/main.yml is missing
    with pytest.raises(
        FileNotFoundError,
        match=f"No such file or directory: '{runtime_tmp.project_dir.absolute()}/meta/main.yaml'",
    ):
        runtime_tmp._install_galaxy_role(runtime_tmp.project_dir)
    # But ignore_errors will return without doing anything
    runtime_tmp._install_galaxy_role(runtime_tmp.project_dir, ignore_errors=True)


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
    caplog.set_level(logging.WARNING)
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
    lower: str | None,
    upper: str | None,
    expected: bool,
) -> None:
    """Validate functioning of version_in_range."""
    runtime = Runtime()
    assert runtime.version_in_range(lower=lower, upper=upper) is expected


@pytest.mark.parametrize(
    ("path", "scenario", "expected_collections"),
    (
        pytest.param(
            "test/collections/acme.goodies",
            "default",
            [
                "ansible.posix",  # from tests/requirements.yml
                "ansible.utils",  # from galaxy.yml
                "community.molecule",  # from galaxy.yml
                "community.crypto",  # from galaxy.yml as a git dependency
            ],
            id="normal",
        ),
        pytest.param(
            "test/collections/acme.goodies/roles/baz",
            "deep_scenario",
            ["community.molecule"],
            id="deep",
        ),
    ),
)
def test_install_collection_from_disk(
    path: str,
    scenario: str,
    expected_collections: list[str],
) -> None:
    """Tests ability to install a local collection."""
    # ensure we do not have acme.goodies installed in user directory as it may
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
        runtime.load_collections()
        for collection_name in expected_collections:
            assert (
                collection_name in runtime.collections
            ), f"{collection_name} not found in {runtime.collections.keys()}"
        runtime.clean()


@pytest.mark.parametrize(
    ("path", "expected_plugins"),
    (
        pytest.param(
            "test/collections/acme.goodies",
            [
                "ansible.posix.patch",  # from tests/requirements.yml
                "community.crypto.acme_account",  # from galaxy.yml as a git dependency
            ],
            id="modules",
        ),
    ),
)
def test_load_plugins(
    path: str,
    expected_plugins: list[str],
) -> None:
    """Tests ability to load plugin from a collection installed by requirement."""
    with cwd(Path(path)):
        from ansible_compat.prerun import get_cache_dir

        rmtree(get_cache_dir(Path.cwd()), ignore_errors=True)
        runtime = Runtime(isolated=True, require_module=True)
        runtime.prepare_environment(install_local=True)
        for plugin_name in expected_plugins:
            loaded_module = module_loader.find_plugin_with_context(
                plugin_name,
                ignore_deprecated=True,
                check_aliases=True,
            )
            assert (
                loaded_module.resolved_fqcn is not None
            ), f"Unable to load module {plugin_name}"

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


def test_load_collections_failure(mocker: MockerFixture) -> None:
    """Tests for ansible-galaxy erroring."""
    mocker.patch(
        "ansible_compat.runtime.Runtime.run",
        return_value=CompletedProcess(
            ["x"],
            returncode=1,
            stdout="There was an error",
            stderr="This is the error",
        ),
        autospec=True,
    )
    runtime = Runtime()
    with pytest.raises(RuntimeError, match="Unable to list collections: "):
        runtime.load_collections()


@pytest.mark.parametrize(
    "value",
    ("[]", '{"path": "bad data"}', '{"path": {"ansible.posix": 123}}'),
    ids=["list", "malformed_collection", "bad_collection_data"],
)
def test_load_collections_garbage(value: str, mocker: MockerFixture) -> None:
    """Tests for ansible-galaxy returning bad data."""
    mocker.patch(
        "ansible_compat.runtime.Runtime.run",
        return_value=CompletedProcess(
            ["x"],
            returncode=0,
            stdout=value,
            stderr="",
        ),
        autospec=True,
    )
    runtime = Runtime()
    with pytest.raises(TypeError, match="Unexpected collection data, "):
        runtime.load_collections()


@pytest.mark.parametrize(
    "value",
    ("", '{"path": {123: 456}}'),
    ids=["nothing", "bad_collection_name"],
)
def test_load_collections_invalid_json(value: str, mocker: MockerFixture) -> None:
    """Tests for ansible-galaxy returning bad data."""
    mocker.patch(
        "ansible_compat.runtime.Runtime.run",
        return_value=CompletedProcess(
            ["x"],
            returncode=0,
            stdout=value,
            stderr="",
        ),
        autospec=True,
    )
    runtime = Runtime()
    with pytest.raises(
        RuntimeError,
        match=f"Unable to parse galaxy output as JSON: {value}",
    ):
        runtime.load_collections()


def test_prepare_environment_offline_role(caplog: pytest.LogCaptureFixture) -> None:
    """Ensure that we can make use of offline roles."""
    with cwd(Path("test/roles/acme.missing_deps")):
        runtime = Runtime(isolated=True)
        runtime.prepare_environment(install_local=True, offline=True)
        assert (
            "Skipped installing old role dependencies due to running in offline mode."
            in caplog.text
        )
        assert (
            "Skipped installing collection dependencies due to running in offline mode."
            in caplog.text
        )


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


def test_runtime_plugins(runtime: Runtime) -> None:
    """Tests ability to access detected plugins."""
    assert len(runtime.plugins.cliconf) == 0
    # ansible.netcommon.restconf might be in httpapi
    assert isinstance(runtime.plugins.httpapi, dict)
    # "ansible.netcommon.default" might be in runtime.plugins.netconf
    assert isinstance(runtime.plugins.netconf, dict)
    assert isinstance(runtime.plugins.role, dict)
    assert "become" in runtime.plugins.keyword

    assert "ansible.builtin.sudo" in runtime.plugins.become
    assert "ansible.builtin.memory" in runtime.plugins.cache
    assert "ansible.builtin.default" in runtime.plugins.callback
    assert "ansible.builtin.local" in runtime.plugins.connection
    assert "ansible.builtin.ini" in runtime.plugins.inventory
    assert "ansible.builtin.env" in runtime.plugins.lookup
    assert "ansible.builtin.sh" in runtime.plugins.shell
    assert "ansible.builtin.host_group_vars" in runtime.plugins.vars
    assert "ansible.builtin.file" in runtime.plugins.module
    assert "ansible.builtin.free" in runtime.plugins.strategy
    assert "ansible.builtin.is_abs" in runtime.plugins.test
    assert "ansible.builtin.bool" in runtime.plugins.filter


@pytest.mark.parametrize(
    ("path", "result"),
    (
        pytest.param(
            "test/assets/galaxy_paths",
            ["test/assets/galaxy_paths/foo/galaxy.yml"],
            id="1",
        ),
        pytest.param(
            "test/collections",
            [],  # should find nothing because these folders are not valid namespaces
            id="2",
        ),
        pytest.param(
            "test/assets/galaxy_paths/foo",
            ["test/assets/galaxy_paths/foo/galaxy.yml"],
            id="3",
        ),
    ),
)
def test_galaxy_path(path: str, result: list[str]) -> None:
    """Check behavior of galaxy path search."""
    assert search_galaxy_paths(Path(path)) == result


@pytest.mark.parametrize(
    ("name", "result"),
    (
        pytest.param(
            "foo",
            False,
            id="0",
        ),
        pytest.param(
            "git+git",
            True,
            id="1",
        ),
        pytest.param(
            "git@acme.com",
            True,
            id="2",
        ),
    ),
)
def test_is_url(name: str, result: bool) -> None:
    """Checks functionality of is_url."""
    assert is_url(name) == result


@pytest.mark.parametrize(
    ("dest", "message"),
    (
        ("/invalid/destination", "Collection is symlinked, but not pointing to"),
        (Path.cwd(), "Found symlinked collection, skipping its installation."),
    ),
    ids=["broken", "valid"],
)
def test_prepare_environment_symlink(
    dest: str | Path,
    message: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure avalid symlinks to collections are properly detected."""
    project_dir = Path(__file__).parent / "collections" / "acme.minimal"
    runtime = Runtime(isolated=True, project_dir=project_dir)
    assert runtime.cache_dir
    acme = runtime.cache_dir / "collections" / "ansible_collections" / "acme"
    acme.mkdir(parents=True, exist_ok=True)
    goodies = acme / "minimal"
    rmtree(goodies, ignore_errors=True)
    goodies.unlink(missing_ok=True)
    goodies.symlink_to(dest)
    runtime.prepare_environment(install_local=True)
    assert message in caplog.text


def test_get_galaxy_role_name_invalid() -> None:
    """Verifies that function returns empty string on invalid input."""
    galaxy_infos = {
        "role_name": False,  # <-- invalid data, should be string
    }
    assert _get_galaxy_role_name(galaxy_infos) == ""


def test_runtime_has_playbook() -> None:
    """Tests has_playbook method."""
    runtime = Runtime(require_module=True)

    assert not runtime.has_playbook("this-does-not-exist.yml")
    # call twice to ensure cache is used:
    assert not runtime.has_playbook("this-does-not-exist.yml")

    assert not runtime.has_playbook("this-does-not-exist.yml", basedir=Path())
    # this is part of community.molecule collection
    assert runtime.has_playbook("community.molecule.validate.yml")
