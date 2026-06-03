"""Abstract base class for KCom plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PluginBase(ABC):
    """Base class all KCom plugins must inherit from.

    Plugins are discovered by scanning a plugin directory for subclasses
    of this class.
    """

    #: Human-readable plugin name (must be unique)
    name: str = "BasePlugin"
    #: Semantic version string
    version: str = "0.0.0"
    #: Short description shown in the plugin manager UI
    description: str = ""

    @abstractmethod
    def initialize(self, app: Any) -> None:
        """Called once when the plugin is loaded.

        Args:
            app: The KComApp instance.
        """
        ...

    @abstractmethod
    def teardown(self) -> None:
        """Called before the plugin is unloaded or the app exits."""
        ...
