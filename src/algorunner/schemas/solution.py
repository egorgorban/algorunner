"""Pydantic contracts for the Solution Strategist/Solver/Code Generator
nodes' structured output.

Mirrors schemas/task.py's conventions (Field(..., min_length=1) on every
required free-text field so structurally-empty LLM output is rejected at the
schema layer).
"""

import builtins
import json
import keyword
import re
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from algorunner.schemas.typespec import (
    MAX_CASE_JSON_CHARS,
    TypeNode,
    coerce_value,
    format_type,
    parse_type,
)


# Role labels for curated approaches (D-03, STRAT-02)
ApproachRole = Literal["brute_force", "optimized", "alternative"]


class Approach(BaseModel):
    name: str = Field(..., min_length=1)
    technique: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    role: ApproachRole
    rationale: str = Field(..., min_length=1)


class ApproachList(BaseModel):
    """Container for the Strategist's structured output.

    OpenAI structured-output `response_format` schemas must be a top-level
    object, not a bare array — this wraps `list[Approach]` for that reason.
    Deliberately no `min_length` constraint on `approaches`: the empty-list
    case (STRAT-03/empty) is guarded explicitly in
    `solution_strategist_node`, not at the schema layer, so the same shape
    remains constructible in tests exercising that guard.
    """

    approaches: list[Approach]


_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# The 25 Go keywords plus `main`/`init`, plus predeclared identifiers and the
# harness's imported package names: declaring a top-level func with any of
# these would shadow or collide with what the generated harness relies on.
GO_RESERVED_NAMES = frozenset(
    {
        "break", "case", "chan", "const", "continue", "default", "defer", "else",
        "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
        "map", "package", "range", "return", "select", "struct", "switch", "type",
        "var", "main", "init",
        "append", "cap", "clear", "close", "complex", "copy", "delete", "imag",
        "len", "make", "max", "min", "new", "panic", "print", "println", "real",
        "recover", "string", "int", "float64", "bool", "error", "true", "false",
        "nil", "iota", "any",
        "fmt", "math", "os", "reflect", "sort",
    }
)


class EntryParam(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not _IDENT_RE.fullmatch(value) or keyword.iskeyword(value):
            raise ValueError(f"parameter name {value!r} is not a valid identifier")
        return value

    @field_validator("type")
    @classmethod
    def _valid_type(cls, value: str) -> str:
        return format_type(parse_type(value))


class EntryPoint(BaseModel):
    """The single function both implementations must define (CODE-01/02)."""

    python_name: str = Field(..., min_length=1)
    go_name: str = Field(..., min_length=1)
    params: list[EntryParam]
    return_type: str = Field(..., min_length=1)
    unordered_result: bool

    @field_validator("python_name")
    @classmethod
    def _valid_python_name(cls, value: str) -> str:
        if (
            not _IDENT_RE.fullmatch(value)
            or keyword.iskeyword(value)
            or hasattr(builtins, value)
            or value.startswith("_algorunner")
        ):
            raise ValueError(f"python_name {value!r} is not an allowed function name")
        return value

    @field_validator("go_name")
    @classmethod
    def _valid_go_name(cls, value: str) -> str:
        if (
            not _IDENT_RE.fullmatch(value)
            or value in GO_RESERVED_NAMES
            or value.startswith("algorunner")
        ):
            raise ValueError(f"go_name {value!r} is not an allowed function name")
        return value

    @field_validator("return_type")
    @classmethod
    def _valid_return_type(cls, value: str) -> str:
        return format_type(parse_type(value))

    @model_validator(mode="after")
    def _valid_params(self) -> "EntryPoint":
        if not self.params:
            raise ValueError("entry point needs at least one parameter")
        names = [p.name for p in self.params]
        if len(set(names)) != len(names):
            raise ValueError("entry point parameter names must be unique")
        return self

    def param_nodes(self) -> list[TypeNode]:
        return [parse_type(p.type) for p in self.params]

    def return_node(self) -> TypeNode:
        return parse_type(self.return_type)

    def make_case(
        self,
        *,
        label: str,
        origin: Literal["provided", "generated"],
        args: list[JsonValue],
        expected: JsonValue,
    ) -> "StructuredCase":
        return self.check_case(
            StructuredCase(label=label, origin=origin, args=args, expected=expected)
        )

    def check_case(self, case: "StructuredCase") -> "StructuredCase":
        """Re-validates arity and declared types; returns a normalized case."""
        nodes = self.param_nodes()
        if len(case.args) != len(nodes):
            raise ValueError(
                f"case {case.label!r}: expected {len(nodes)} arguments, got {len(case.args)}"
            )
        args = [
            coerce_value(a, n, path=f"args[{i}]")
            for i, (a, n) in enumerate(zip(case.args, nodes, strict=True))
        ]
        expected = coerce_value(case.expected, self.return_node(), path="expected")
        size = len(json.dumps(args)) + len(json.dumps(expected))
        if size > MAX_CASE_JSON_CHARS:
            raise ValueError(
                f"case {case.label!r}: JSON size {size} exceeds {MAX_CASE_JSON_CHARS} characters"
            )
        return StructuredCase(
            label=case.label,
            origin=case.origin,
            args=args,  # type: ignore[arg-type]
            expected=expected,  # type: ignore[arg-type]
        )


class StructuredCase(BaseModel):
    """Language-neutral test case: JSON values typed against an EntryPoint
    (CODE-03/04, D-12 - no target-language expression strings)."""

    label: str = Field(..., min_length=1)
    origin: Literal["provided", "generated"]
    args: list[JsonValue]
    expected: JsonValue


class Solution(BaseModel):
    approach: Approach
    algorithm: str = Field(..., min_length=1)
    entry_point: EntryPoint
    code_python: str = Field(..., min_length=1)
    code_go: str = Field(..., min_length=1)
    tests: list[StructuredCase]
    complexity_time: str = Field(..., min_length=1)
    complexity_space: str = Field(..., min_length=1)
