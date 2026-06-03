"""Singleton metaclass utility."""

from __future__ import annotations

from typing import Any


class SingletonMeta(type):
    """Thread-safe singleton metaclass.

    Usage::

        class MyClass(metaclass=SingletonMeta):
            pass
    """

    _instances: dict[type, Any] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
