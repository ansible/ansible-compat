"""Tests for _version module."""


def test_version_module() -> None:
    """Tests that _version exports are present."""
    # import kept here to allow mypy/pylint to run when module is not installed
    # and the generated _version.py is missing.
    # pylint: disable=no-name-in-module,no-member
    import ansible_compat._version  # type: ignore[import-not-found,unused-ignore]

    assert ansible_compat._version.__version__
    assert ansible_compat._version.__version_tuple__
    assert ansible_compat._version.version
