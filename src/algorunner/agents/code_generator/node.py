"""Code Generator graph node.

Constructs the real `Solution` (schemas/solution.py) from
`state["solver_output"]` plus freshly LLM-generated `entry_point`,
`code_python` and `code_go`, with `tests=[]` - the Test Generator node fills
this in next.

`CodeGenOutput` is a local, narrower structured-output schema: the LLM call is
responsible for the entry-point declaration and the two code strings, while
`Solution`'s approach/algorithm/complexity/tests shape is assembled here from
`state["solver_output"]` (mirroring `solver/node.py`'s `SolverOutput`).

CODE-01/02: the declared entry point is confirmed by deterministic checks that
both code strings really define it, so the harness renderers never call a
function that does not exist. Failures raise (D-00f) and are not retried.
"""

import re

from pydantic import BaseModel, Field

from algorunner.agents.code_generator.prompts import build_code_messages
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.solution import EntryPoint, Solution


class CodeGenOutput(BaseModel):
    entry_point: EntryPoint
    code_python: str = Field(..., min_length=1)
    code_go: str = Field(..., min_length=1)


def _validate_code(result: CodeGenOutput) -> None:
    """D-00f: surfaced as ValueError naming the failed rule, never retried."""
    ep = result.entry_point
    if not re.search(rf"^def\s+{re.escape(ep.python_name)}\s*\(", result.code_python, re.MULTILINE):
        raise ValueError(
            f"Code Generator: code_python has no top-level `def {ep.python_name}(`"
        )
    if not re.search(rf"^func\s+{re.escape(ep.go_name)}\s*\(", result.code_go, re.MULTILINE):
        raise ValueError(f"Code Generator: code_go has no top-level `func {ep.go_name}(`")
    if re.search(r"^func\s+main\s*\(", result.code_go, re.MULTILINE):
        raise ValueError(
            "Code Generator: code_go must not declare `func main` (the harness supplies it)"
        )
    if not re.search(r"^package\s+main\b", result.code_go, re.MULTILINE):
        raise ValueError("Code Generator: code_go must start with `package main`")


async def code_generator_node(state: GraphState) -> dict:
    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("code_generator"),
        messages=build_code_messages(state),
        response_format=CodeGenOutput,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Code Generator refused or failed to parse: {message.refusal}")
    result = message.parsed
    _validate_code(result)
    solver_output = state["solver_output"]
    solution = Solution(
        approach=solver_output["approach"],
        algorithm=solver_output["algorithm"],
        entry_point=result.entry_point,
        code_python=result.code_python,
        code_go=result.code_go,
        tests=[],
        complexity_time=solver_output["complexity_time"],
        complexity_space=solver_output["complexity_space"],
    )
    return {"solution": solution}
