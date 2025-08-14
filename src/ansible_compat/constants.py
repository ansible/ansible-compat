"""Constants used by ansible_compat."""

from pathlib import Path

META_MAIN = (Path("meta") / Path("main.yml"), Path("meta") / Path("main.yaml"))
REQUIREMENT_LOCATIONS = [
    "requirements.yml",
    "roles/requirements.yml",
    "collections/requirements.yml",
    # These is more of less the official way to store test requirements in collections so far, comments shows number of repos using this reported by https://sourcegraph.com/ at the time of writing
    "tests/requirements.yml",  # 170
    "tests/integration/requirements.yml",  # 3
    "tests/unit/requirements.yml",  # 1
]

# Minimal version of Ansible we support for runtime
ANSIBLE_MIN_VERSION = "2.16"

# ansible-lint version below which we auto-enable plugin loader for backwards compatibility
ANSIBLE_LINT_MIN_VERSION_EARLY_LOADER = "25.8.1"

# Based on https://docs.ansible.com/ansible/latest/reference_appendices/config.html
ANSIBLE_DEFAULT_ROLES_PATH = (
    "~/.ansible/roles:/usr/share/ansible/roles:/etc/ansible/roles"
)

INVALID_CONFIG_RC = 2
ANSIBLE_MISSING_RC = 4
INVALID_PREREQUISITES_RC = 10

MSG_INVALID_FQRL = """\
Computed fully qualified role name of {0} does not follow current galaxy requirements.
Please edit meta/main.yml and assure we can correctly determine full role name:

galaxy_info:
role_name: my_name  # if absent directory name hosting role is used instead
namespace: my_galaxy_namespace  # if absent, author is used instead

Namespace: https://old-galaxy.ansible.com/docs/contributing/namespaces.html#galaxy-namespace-limitations
Role: https://old-galaxy.ansible.com/docs/contributing/creating_role.html#role-names

As an alternative, you can add 'role-name' to either skip_list or warn_list.
"""

RC_ANSIBLE_OPTIONS_ERROR = 5
