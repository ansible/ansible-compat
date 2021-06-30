"""Module to deal with errors."""
from ansible_compat.constants import ANSIBLE_MISSING_RC, INVALID_PREREQUISITES_RC


class AnsibleCompatError(RuntimeError):
    """Generic error originating from ansible_compat library."""

    code = 1  # generic error


class MissingAnsibleError(AnsibleCompatError):
    """Reports a missing or broken Ansible installation."""

    code = ANSIBLE_MISSING_RC


class InvalidPrerequisiteError(AnsibleCompatError):
    """Reports a missing requirement."""

    code = INVALID_PREREQUISITES_RC
