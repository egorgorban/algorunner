"""Solver graph node for per-approach branch execution (Phase 3).

Elaborates the branch's own approach (`state["approach"]`) into an algorithm
description + complexity reasoning. In Phase 3, each branch runs the Solver
on its own approach; in Phase 2 this elaborated approaches[0] deterministically.

`schemas/solution.py`'s `Solution` model requires non-empty
`code_python`/`code_go`/`tests` (Phase 2 Field constraints), and this
node does not yet produce them, so `SolverOutput` is a separate, narrower,
module-local schema — not a durable inter-plan contract. The Code Generator
constructs the real `Solution` once code/tests exist.
"""

import logging

from pydantic import BaseModel, Field

from algorunner.agents.solver.prompts import build_solver_messages
from algorunner.graph.state import ApproachState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured

logger = logging.getLogger(__name__)


class SolverOutput(BaseModel):
    algorithm: str = Field(..., min_length=1)
    complexity_time: str = Field(..., min_length=1)
    complexity_space: str = Field(..., min_length=1)


async def solver_node(state: ApproachState) -> dict:
    """Solve the branch's own approach.

    Reads state["approach"] (the branch's dedicated approach) and elaborates
    it into algorithm description and complexity reasoning.
    """
    logger.debug(f"solver_node: Entry state keys: {list(state.keys())}")
    logger.debug(f"solver_node: approach_idx={state.get('approach_idx')}, review={state.get('review')}")

    approach = state["approach"]
    logger.info(f"solver_node: Elaborating approach {approach.name}")

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
    logger.info(f"solver_node: Successfully elaborated {approach.name}")
    return {
        "solver_output": {
            "approach": approach,
            "algorithm": result.algorithm,
            "complexity_time": result.complexity_time,
            "complexity_space": result.complexity_space,
        }
    }
