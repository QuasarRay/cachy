"""CachyOS hybrid pipeline implementation."""

from __future__ import annotations

from typing import Any

__all__ = ["CachyPipeline"]


def __getattr__(name: str) -> Any:
    """Expose Dagger's main object without coupling pure contract imports to the SDK."""
    if name == "CachyPipeline":
        from .main import CachyPipeline

        return CachyPipeline
    raise AttributeError(name)
