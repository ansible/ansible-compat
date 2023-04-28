"""Utilities for loading various files."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ansible_compat.errors import InvalidPrerequisiteError


def yaml_from_file(path: Path) -> Any:
    """Return a loaded YAML file."""
    with path.open(encoding="utf-8") as content:
        return yaml.load(content, Loader=yaml.FullLoader)


def colpath_from_path(path: Path) -> str | None:
    """Return a FQCN from a path."""
    galaxy_file = path / "galaxy.yml"
    if galaxy_file.exists():
        galaxy = yaml_from_file(galaxy_file)
        for k in ("namespace", "name"):
            if k not in galaxy:
                raise InvalidPrerequisiteError(
                    f"{galaxy_file} is missing the following mandatory field {k}"
                )
        return f"{galaxy['namespace']}/{galaxy['name']}"
    return None
