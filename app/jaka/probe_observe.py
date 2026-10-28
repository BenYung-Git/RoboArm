"""Helpers to record get_controller_ip return values without interpreting them."""

from __future__ import annotations

from typing import Any

_REPR_LIMIT = 2000
_ELEM_REPR_LIMIT = 1000


def clipped_repr(value: Any, limit: int = _REPR_LIMIT) -> str:
    text = repr(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def observe_value(value: Any) -> dict[str, Any]:
    """
    Describe a return value for logging only.
    Does not assume list/str formats or map non-zero codes to 'no devices'.
    """
    obs: dict[str, Any] = {
        "type_name": type(value).__name__,
        "module": getattr(type(value), "__module__", None),
        "repr": clipped_repr(value),
        "is_tuple": isinstance(value, tuple),
    }
    if isinstance(value, tuple):
        obs["tuple_len"] = len(value)
        elements: list[dict[str, Any]] = []
        for index, item in enumerate(value):
            elements.append(
                {
                    "index": index,
                    "type_name": type(item).__name__,
                    "module": getattr(type(item), "__module__", None),
                    "repr": clipped_repr(item, _ELEM_REPR_LIMIT),
                }
            )
        obs["elements"] = elements
    return obs
