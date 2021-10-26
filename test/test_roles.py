"""Tests Role class."""
import pytest

from ansible_compat.roles import Role


@pytest.mark.parametrize(
    ("role_name", "is_valid"),
    (
        ("x.y.z", False),  # 3 dots unexpected
        ("foo-bar", False),  # dash not allowed
        ("foo_bar", False),  # missing namespace
        ("ns.foo-bar", False),  # dash not allowed
        ("ns.foo_bar", True),
        ("for.foo", False),  # 'for' is python identifier
        ("ns.for", False),  # 'for' is python identifier
    ),
)
def test_role_fail(role_name: str, is_valid: bool) -> None:
    """Check if Role.validate returns expected result."""
    role = Role(role_name)
    assert role.is_valid() is is_valid
