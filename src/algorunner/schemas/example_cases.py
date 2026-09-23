"""Provided example free text -> StructuredCase.

D-10: provided examples are ground truth. Deterministic parsing is therefore
authoritative wherever it succeeds (LeetCode-style ``name = value, ...`` input
with a strict-JSON output); anything else is normalized by the Test Generator's
LLM call and then verified here in Python, never trusted blindly.
"""

import math
import re

from algorunner.schemas.solution import EntryPoint, StructuredCase
from algorunner.schemas.typespec import coerce_value, parse_json_text

_INPUT_PREFIX_RE = re.compile(r"^\s*input\s*:\s*", re.IGNORECASE)
_OUTPUT_PREFIX_RE = re.compile(r"^\s*output\s*:\s*", re.IGNORECASE)
_SEGMENT_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*", re.DOTALL)

_OPEN = "[{("
_CLOSE = "]})"


def _label(index: int) -> str:
    return f"provided example {index}"


def _split_top_level(text: str) -> list[str] | None:
    """Splits on commas outside brackets and double-quoted strings. Returns
    None for unbalanced text."""
    parts: list[str] = []
    stack: list[str] = []
    current: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            current.append(ch)
        elif ch in _OPEN:
            stack.append(_CLOSE[_OPEN.index(ch)])
            current.append(ch)
        elif ch in _CLOSE:
            if not stack or stack.pop() != ch:
                return None
            current.append(ch)
        elif ch == "," and not stack:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if in_string or stack:
        return None
    parts.append("".join(current))
    return parts


def parse_provided_example(
    entry_point: EntryPoint, *, index: int, input_text: str, output_text: str
) -> StructuredCase | None:
    """Deterministic conversion; returns None (never raises) when the example
    cannot be parsed and type-checked."""
    try:
        body = _INPUT_PREFIX_RE.sub("", input_text, count=1).strip()
        segments = _split_top_level(body)
        if not segments:
            return None
        names: list[str] = []
        values: list[object] = []
        for segment in segments:
            match = _SEGMENT_RE.fullmatch(segment)
            if match is None:
                return None
            names.append(match.group(1))
            values.append(parse_json_text(match.group(2)))
        param_names = [p.name for p in entry_point.params]
        if len(set(names)) == len(names) and set(names) == set(param_names):
            by_name = dict(zip(names, values, strict=True))
            args = [by_name[n] for n in param_names]
        elif len(values) == len(param_names):
            args = values
        else:
            return None
        expected = parse_json_text(_OUTPUT_PREFIX_RE.sub("", output_text, count=1).strip())
        return entry_point.make_case(
            label=_label(index), origin="provided", args=args, expected=expected  # type: ignore[arg-type]
        )
    except (ValueError, TypeError):
        return None


def _equal(a: object, b: object) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return (
            isinstance(a, (int, float))
            and isinstance(b, (int, float))
            and not isinstance(a, bool)
            and not isinstance(b, bool)
            and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
        )
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b, strict=True))
    return type(a) is type(b) and a == b


def build_normalized_example(
    entry_point: EntryPoint,
    *,
    index: int,
    output_text: str,
    args_json: str,
    expected_json: str,
) -> StructuredCase:
    """Verifies an LLM-normalized example (D-10, D-00f: raise, never coerce
    silently)."""
    try:
        args = parse_json_text(args_json)
        if not isinstance(args, list):
            raise ValueError("args_json must be a JSON array of positional arguments")
        expected = parse_json_text(expected_json)
        case = entry_point.make_case(
            label=_label(index), origin="provided", args=args, expected=expected  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise ValueError(f"normalized example index {index} is invalid: {exc}") from exc

    try:
        stated = parse_json_text(_OUTPUT_PREFIX_RE.sub("", output_text, count=1).strip())
        stated = coerce_value(stated, entry_point.return_node(), path="output")
    except ValueError:
        return case  # output is not strict JSON of the return type: type check above is the guard
    if not _equal(stated, case.expected):
        raise ValueError(
            f"normalized example index {index} disagrees with the provided output: "
            f"normalized expected {case.expected!r}, example output {stated!r}"
        )
    return case
