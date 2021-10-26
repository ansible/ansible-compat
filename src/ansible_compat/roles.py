"""Wrapper class for Ansible Roles."""
import re
from keyword import iskeyword


class Role:
    """Utility class for validating roles."""

    name_re = re.compile(r"[a-z\d_]+")

    def __init__(self, name: str):
        """Instantiate an Ansible role."""
        self.namespace = ""
        if name.count(".") == 1:
            self.namespace, self.name = name.split(".")
        else:
            self.name = name

    def is_valid(self) -> bool:
        """Return false if role is not properly named.

        In the future other tests may be added to validate().
        """
        return all(
            (self.name_re.fullmatch(x) and str.isidentifier(x) and not iskeyword(x))
            for x in (self.namespace, self.name)
        )

    def __repr__(self) -> str:
        """Return string representation of role."""
        if self.namespace:
            return f"{self.namespace}.{self.name}"
        return self.name
