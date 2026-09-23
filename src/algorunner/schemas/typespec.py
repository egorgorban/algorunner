"""Closed, language-neutral type vocabulary shared by the entry-point contract,
the structured test cases, the prompts and the per-language harness renderers.

Vocabulary (plan 02-09, F2): ``int``, ``float``, ``bool``, ``str`` and nested
``list[T]``. Anything else cannot be declared and fails loudly (D-00f).

This module is dependency-free on purpose (standard library only) so prompts
and validators can both import it without cycles.
"""

import json
import math
from dataclasses import dataclass
from typing import Literal

MAX_CASES = 100
MAX_CASE_JSON_CHARS = 20000
MAX_LIST_DEPTH = 4

INT_MIN = -(2**63)
INT_MAX = 2**63 - 1

TYPE_VOCABULARY_DOC = (
    "Types are drawn from a closed vocabulary: int, float, bool, str, and "
    "list[T] where T is again one of these (lists may nest, for example "
    "list[list[int]]). Nothing else is allowed: no dict, tuple, Optional, "
    "None, custom classes, linked lists or trees. JSON encoding of values: "
    "int is a JSON integer within the signed 64-bit range, float is a JSON "
    "number, bool is true or false, str is a JSON string, list is a JSON "
    "array; NaN and Infinity are not allowed. Go mapping: int -> int, "
    "float -> float64, bool -> bool, str -> string, list[T] -> []T. "
    "Python uses the matching built-in types (list[T] is a Python list)."
)

Kind = Literal["int", "float", "bool", "str", "list"]
_SCALARS = ("int", "float", "bool", "str")


@dataclass(frozen=True)
class TypeNode:
    kind: Kind
    element: "TypeNode | None" = None


def parse_type(text: str) -> TypeNode:
    """Parses ``int | float | bool | str | list[<type>]`` (whitespace
    tolerant, at most ``MAX_LIST_DEPTH`` nested lists)."""
    if not isinstance(text, str):
        raise ValueError(f"type must be a string, got {type(text).__name__}")
    return _parse(text.strip(), depth=0)


def _parse(text: str, *, depth: int) -> TypeNode:
    if text in _SCALARS:
        return TypeNode(kind=text)  # type: ignore[arg-type]
    if text.startswith("list"):
        rest = text[4:].lstrip()
        if rest.startswith("[") and rest.endswith("]"):
            if depth + 1 > MAX_LIST_DEPTH:
                raise ValueError(
                    f"type {text!r} nests lists deeper than {MAX_LIST_DEPTH} levels"
                )
            inner = rest[1:-1].strip()
            if not inner:
                raise ValueError("list type needs an element type, got empty list[]")
            return TypeNode(kind="list", element=_parse(inner, depth=depth + 1))
    raise ValueError(
        f"unsupported type {text!r}: allowed are int, float, bool, str and list[T]"
    )


def format_type(node: TypeNode) -> str:
    if node.kind == "list":
        assert node.element is not None
        return f"list[{format_type(node.element)}]"
    return node.kind


def coerce_value(value: object, node: TypeNode, *, path: str = "value") -> object:
    """Validates ``value`` against ``node`` and returns the normalized JSON
    value. Raises ValueError naming ``path`` on any mismatch."""
    kind = node.kind
    if kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError(f"{path}: expected bool, got {_describe(value)}")
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{path}: expected int, got {_describe(value)}")
        if not INT_MIN <= value <= INT_MAX:
            raise ValueError(f"{path}: int {value} is outside the signed 64-bit range")
        return value
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: expected float, got {_describe(value)}")
        if isinstance(value, int) and not INT_MIN <= value <= INT_MAX:
            raise ValueError(f"{path}: number {value} is outside the signed 64-bit range")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{path}: float must be finite, got {value!r}")
        return result
    if kind == "str":
        if not isinstance(value, str):
            raise ValueError(f"{path}: expected str, got {_describe(value)}")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{path}: string is not valid UTF-8 text ({exc.reason})") from exc
        return value
    # list
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected list, got {_describe(value)}")
    assert node.element is not None
    return [
        coerce_value(item, node.element, path=f"{path}[{i}]") for i, item in enumerate(value)
    ]


def _describe(value: object) -> str:
    text = repr(value)
    if len(text) > 60:
        text = text[:57] + "..."
    return f"{type(value).__name__} {text}"


def _reject_constant(name: str) -> object:
    raise ValueError(f"JSON constant {name} is not allowed")


def parse_json_text(text: str) -> object:
    """Strict ``json.loads``: NaN/Infinity rejected, decode errors re-raised
    as ValueError."""
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg} (at position {exc.pos})") from exc
    except RecursionError as exc:
        raise ValueError("invalid JSON: nesting too deep") from exc
