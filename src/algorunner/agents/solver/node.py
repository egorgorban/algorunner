"""Solver graph node.

Elaborates `state["approaches"][0]` — the deterministically-selected first
approach in the Strategist's returned list, no re-sorting/re-ranking — into
an algorithm description + complexity reasoning.

`schemas/solution.py`'s `Solution` model requires non-empty
`code_python`/`code_go`/`tests` (Plan 02-01's Field constraints), and this
node does not yet produce them, so `SolverOutput` is a separate, narrower,
module-local schema for this plan's partial elaboration — not a durable
inter-plan contract. Plan 02-04's Code Generator constructs the real
`Solution` once code/tests exist, folding this dict in.
"""

from pydantic import BaseModel, Field

from algorunner.agents.solver.prompts import build_solver_messages
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured


class SolverOutput(BaseModel):
    algorithm: str = Field(..., min_length=1)
    complexity_time: str = Field(..., min_length=1)
    complexity_space: str = Field(..., min_length=1)


async def solver_node(state: GraphState) -> dict:
    approach = state["approaches"][0]
    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("solver"),
        messages=build_solver_messages(state),
        response_format=SolverOutput,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Solver refused or failed to parse: {message.refusal}")
    result = message.parsed
    return {
        "solver_output": {
            "approach": approach,
            "algorithm": result.algorithm,
            "complexity_time": result.complexity_time,
            "complexity_space": result.complexity_space,
        }
    }
