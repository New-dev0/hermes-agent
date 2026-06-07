"""Runtime-resolved path helpers for profile-scoped tool modules."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Union


PathInput = Union[str, Path, "RuntimePath"]


class RuntimePath:
    """Path-like proxy that resolves from a callable at use time.

    Hermes API requests can bind ``HERMES_HOME`` through a context-local
    override, so modules must not freeze profile paths during import.  This
    proxy keeps legacy public constants path-like while preserving runtime
    scoping.
    """

    def __init__(self, resolver: Callable[[], Path], label: str):
        self._resolver = resolver
        self._label = label

    def path(self) -> Path:
        return Path(self._resolver())

    def __fspath__(self) -> str:
        return str(self.path())

    def __str__(self) -> str:
        return str(self.path())

    def __repr__(self) -> str:
        return f"RuntimePath({self._label!r}, current={str(self.path())!r})"

    def __truediv__(self, key) -> Path:
        return self.path() / key

    def __rtruediv__(self, key) -> Path:
        return Path(key) / self.path()

    def __eq__(self, other) -> bool:
        try:
            return self.path() == runtime_path(other)
        except TypeError:
            return False

    def __hash__(self) -> int:
        return hash(self.path())

    def __getattr__(self, name: str):
        return getattr(self.path(), name)


def runtime_path(value: PathInput) -> Path:
    if isinstance(value, RuntimePath):
        return value.path()
    return Path(value)
