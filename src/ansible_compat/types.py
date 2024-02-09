"""Custom types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Union

try:  # py39 does not have TypeAlias
    from typing_extensions import TypeAlias
except ImportError:
    from typing import TypeAlias  # type: ignore[no-redef,attr-defined]

JSON: TypeAlias = Union[dict[str, "JSON"], list["JSON"], str, int, float, bool, None]
JSON_ro: TypeAlias = Union[
    Mapping[str, "JSON_ro"],
    Sequence["JSON_ro"],
    str,
    int,
    float,
    bool,
    None,
]

__all__ = ["JSON", "JSON_ro"]
