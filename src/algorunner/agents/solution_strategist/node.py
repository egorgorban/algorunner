"""Solution Strategist graph node.

Calls the LLM with `response_format=ApproachList` (a container schema, since
OpenAI structured-output top-level schemas must be an object, not a bare
array) and explicitly guards the empty-approaches case (STRAT-03/empty):
`if not result.approaches: raise ValueError(...)`. This ValueError is caught
by `worker/tasks.py`'s existing CR-01 try/except (Plan 02-02) and surfaces
as a structured `TaskError` — no second exception-handling layer is added
here.

Accesses `client_factory`/`call_structured` through the module (not
imported by name) so `tests/conftest.py`'s `mock_openai_parse`-style
monkeypatching takes effect regardless of import order, mirroring
`problem_analyzer/node.py`.
"""

from algorunner.agents.solution_strategist.prompts import build_strategy_messages
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.solution import ApproachList


async def solution_strategist_node(state: GraphState) -> dict:
    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("solution_strategist"),
        messages=build_strategy_messages(state),
        response_format=ApproachList,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Strategist refused or failed to parse: {message.refusal}")
    result = message.parsed
    if not result.approaches:
        raise ValueError("Strategist returned zero approaches")
    return {"approaches": result.approaches}
