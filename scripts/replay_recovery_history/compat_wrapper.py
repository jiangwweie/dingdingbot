"""Helpers for historical script compatibility wrappers."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any


def install_compat_exports(target_globals: dict[str, Any], module_name: str) -> ModuleType:
    module = import_module(module_name)
    for name, value in vars(module).items():
        if name.startswith("__") and name.endswith("__"):
            continue
        target_globals[name] = value

    def _compat_main(*args: Any, **kwargs: Any) -> Any:
        for name, value in list(target_globals.items()):
            if name.startswith("__") and name.endswith("__"):
                continue
            if name in {"_archived_module", "_main", "main"}:
                continue
            setattr(module, name, value)
        return module.main(*args, **kwargs)

    target_globals["_archived_module"] = module
    target_globals["_main"] = _compat_main
    target_globals["main"] = _compat_main
    return module
