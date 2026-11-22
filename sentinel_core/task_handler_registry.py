"""Explicit registry for workflow task handlers; execution is delegated to adapters."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")


@dataclass(frozen=True)
class TaskHandlerSpec:
    name: str
    version: str
    handler: Callable[..., Any]
    input_validator: Callable[[Any], bool] | None = None


class TaskHandlerRegistry:
    """Register and resolve handlers without invoking them or performing side effects."""

    def __init__(self):
        self._handlers: dict[str, TaskHandlerSpec] = {}

    @staticmethod
    def _valid_name(name: Any) -> bool:
        return isinstance(name, str) and bool(_NAME_PATTERN.fullmatch(name))

    @staticmethod
    def _valid_version(version: Any) -> bool:
        return isinstance(version, str) and bool(_VERSION_PATTERN.fullmatch(version))

    def register(self, name: str, handler: Callable[..., Any], version: str = "1", input_validator: Callable[[Any], bool] | None = None) -> dict:
        if not self._valid_name(name):
            return {"action": "blocked", "reason": "handler_name_invalid"}
        if not callable(handler):
            return {"action": "blocked", "reason": "handler_not_callable"}
        if not self._valid_version(version):
            return {"action": "blocked", "reason": "handler_version_invalid"}
        if input_validator is not None and not callable(input_validator):
            return {"action": "blocked", "reason": "validator_not_callable"}
        if name in self._handlers:
            return {"action": "blocked", "reason": "handler_duplicate"}
        self._handlers[name] = TaskHandlerSpec(name, version, handler, input_validator)
        return {"action": "registered", "name": name, "version": version}

    def resolve(self, name: str, version: str | None = None) -> dict:
        if not self._valid_name(name):
            return {"action": "blocked", "reason": "handler_name_invalid"}
        spec = self._handlers.get(name)
        if spec is None:
            return {"action": "not_found"}
        if version is not None:
            if not self._valid_version(version):
                return {"action": "blocked", "reason": "handler_version_invalid"}
            if spec.version != version:
                return {"action": "version_mismatch", "registered_version": spec.version}
        return {"action": "resolved", "handler": spec.handler, "name": spec.name, "version": spec.version, "input_validator": spec.input_validator}

    def validate_input(self, name: str, payload: Any, version: str | None = None) -> dict:
        resolved = self.resolve(name, version)
        if resolved.get("action") != "resolved":
            return resolved
        validator = resolved["input_validator"]
        if validator is None:
            return {"action": "valid", "name": name, "version": resolved["version"]}
        try:
            accepted = validator(payload)
        except Exception:
            return {"action": "blocked", "reason": "input_validator_error"}
        if accepted is not True:
            return {"action": "blocked", "reason": "input_invalid"}
        return {"action": "valid", "name": name, "version": resolved["version"]}

    def list_handlers(self) -> dict:
        return {"action": "listed", "handlers": [
            {"name": spec.name, "version": spec.version, "has_input_validator": spec.input_validator is not None}
            for spec in sorted(self._handlers.values(), key=lambda item: item.name)
        ]}

    def unregister(self, name: str, version: str | None = None) -> dict:
        resolved = self.resolve(name, version)
        if resolved.get("action") != "resolved":
            return resolved
        del self._handlers[name]
        return {"action": "unregistered", "name": name, "version": resolved["version"]}
