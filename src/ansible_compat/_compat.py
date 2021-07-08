"""Internal compatibility shims."""
import logging
from typing import Any, Callable, TypeVar

try:
    import tenacity

    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

WrappedFn = TypeVar("WrappedFn", bound=Callable[..., Any])
_logger = logging.getLogger(__name__)


def noop_dec(f: WrappedFn) -> WrappedFn:
    """Decorate function with a no-op."""
    return f


retry = noop_dec
if HAS_TENACITY:
    retry = tenacity.retry(
        reraise=True,
        wait=tenacity.wait_fixed(30),  # type: ignore
        stop=tenacity.stop_after_attempt(3),  # type: ignore
        before_sleep=tenacity.after_log(_logger, logging.WARNING),  # type: ignore
    )


__all__ = ("retry",)
