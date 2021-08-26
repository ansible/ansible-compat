"""Portability helpers."""
import sys

# Based on workarounds seen on https://github.com/python/mypy/issues/1362
if sys.version_info >= (3, 8):
    from functools import cached_property
else:
    from cached_property import cached_property

if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    cache = lru_cache(maxsize=None)


__all__ = ["cache", "cached_property"]
