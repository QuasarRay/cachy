"""CachyOS hybrid pipeline implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .main import CachyPipeline as CachyPipeline

__all__ = ["CachyPipeline"]


def __getattr__(name: str) -> Any:
    """Load the Dagger main object only when the runtime asks for it.

    Contract and architecture modules are deliberately importable without the
    Dagger SDK so their pure validation tests remain independent and hermetic.
    """
    if name == "CachyPipeline":
        from .main import CachyPipeline

        return CachyPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
