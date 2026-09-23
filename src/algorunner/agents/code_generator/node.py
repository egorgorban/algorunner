"""Code Generator graph node.

Constructs the real `Solution` (schemas/solution.py) from
`state["solver_output"]` plus freshly LLM-generated `code_python`/
`code_go`, with `tests=[]` — the Test Generator node fills this in next.

`CodeGenOutput` is a local, narrower structured-output schema (not added to
schemas/solution.py): the LLM call itself is only responsible for the two
code strings, while `Solution`'s full approach/algorithm/complexity/tests
shape is assembled here by hand from `state["solver_output"]` plus the LLM's
two code fields — mirroring `solver/node.py`'s `SolverOutput` pattern.
"""

from pydantic import BaseModel, Field

from algorunner.agents.code_generator.prompts import build_code_messages
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.solution import Solution


class CodeGenOutput(BaseModel):
    code_python: str = Field(..., min_length=1)
    code_go: str = Field(..., min_length=1)


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
    solver_output = state["solver_output"]
    solution = Solution(
        approach=solver_output["approach"],
        algorithm=solver_output["algorithm"],
        code_python=result.code_python,
        code_go=result.code_go,
        tests=[],
        complexity_time=solver_output["complexity_time"],
        complexity_space=solver_output["complexity_space"],
    )
    return {"solution": solution}
