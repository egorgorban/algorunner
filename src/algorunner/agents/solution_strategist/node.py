"""Solution Strategist graph node.

Calls the LLM with `response_format=ApproachList` (a container schema, since
OpenAI structured-output top-level schemas must be an object, not a bare
array) and explicitly guards the empty-approaches case (STRAT-03/empty):
`if not result.approaches: raise ValueError(...)`. This ValueError is caught
by `worker/tasks.py`'s existing CR-01 try/except (Plan 02-02) and surfaces
as a structured `TaskError` — no second exception-handling layer is added
here.

Curation (D-01, D-03): deduplicates approaches by normalized name and enforces
the max_approaches cap (settings.max_approaches, default 3). Logs one warning
if anything was dropped.

Accesses `client_factory`/`call_structured` through the module (not
imported by name) so `tests/conftest.py`'s `mock_openai_parse`-style
monkeypatching takes effect regardless of import order, mirroring
`problem_analyzer/node.py`.
"""

import logging

from langgraph.types import Overwrite

from algorunner.agents.solution_strategist.prompts import build_strategy_messages
from algorunner.config import settings
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.solution import ApproachList

logger = logging.getLogger(__name__)


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

    # Curation: dedup by normalized name, enforce max_approaches cap (D-01, D-03)
    initial_count = len(result.approaches)
    seen_normalized_names = set()
    kept = []

    for approach in result.approaches:
        # Normalize name: collapse whitespace and lowercase
        normalized_name = " ".join(approach.name.split()).casefold()

        if normalized_name not in seen_normalized_names:
            seen_normalized_names.add(normalized_name)
            kept.append(approach)

    # Truncate to max_approaches
    kept = kept[:settings.max_approaches]
    final_count = len(kept)

    # Log warning if anything was dropped
    if final_count < initial_count:
        logger.warning(
            f"Strategist returned {initial_count} approaches; "
            f"kept {final_count} after dedup and cap to {settings.max_approaches}"
        )

    # Reset approach_outcomes for idempotent re-invoke (Pitfall 3, D-09)
    return {
        "approaches": kept,
        "approach_outcomes": Overwrite({}),
    }
