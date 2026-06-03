"""Plugin discovery and lifecycle management."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from kcom.plugins.plugin_base import PluginBase


class PluginLoader:
    """Discovers, loads, and unloads KCom plugins.

    Plugin files are standalone .py modules that define at least one
    subclass of PluginBase.
    """

    def __init__(self) -> None:
        self._loaded: dict[str, PluginBase] = {}  # name → instance

    def discover(self, plugin_dir: Path) -> list[type[PluginBase]]:
        """Scan a directory for Python files and return all PluginBase subclasses found.

        Args:
            plugin_dir: Directory to scan (non-recursive).

        Returns:
            List of PluginBase subclasses discovered.
        """
        found: list[type[PluginBase]] = []
        if not plugin_dir.is_dir():
            return found

        for py_file in sorted(plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"kcom_plugin_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)  # type: ignore[attr-defined]

                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, PluginBase)
                        and obj is not PluginBase
                    ):
                        found.append(obj)
            except Exception as e:
                print(f"[PluginLoader] Failed to load {py_file}: {e}")

        return found

    def load(self, plugin_class: type[PluginBase], app: Any) -> bool:
        """Instantiate a plugin class and call its initialize() method.

        Returns True on success.
        """
        name = plugin_class.name
        if name in self._loaded:
            return True  # already loaded

        try:
            instance = plugin_class()
            instance.initialize(app)
            self._loaded[name] = instance
            return True
        except Exception as e:
            print(f"[PluginLoader] Failed to initialize plugin {name!r}: {e}")
            return False

    def unload(self, name: str) -> bool:
        """Call teardown() and remove a loaded plugin.

        Returns True if the plugin was found and unloaded.
        """
        instance = self._loaded.pop(name, None)
        if instance is None:
            return False
        try:
            instance.teardown()
        except Exception as e:
            print(f"[PluginLoader] Error during teardown of {name!r}: {e}")
        return True

    def unload_all(self) -> None:
        for name in list(self._loaded.keys()):
            self.unload(name)

    @property
    def loaded_plugins(self) -> dict[str, PluginBase]:
        return dict(self._loaded)
