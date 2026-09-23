"""Problem Analyzer graph node — the first real OpenAI-backed LangGraph node.

Calls Plan 02-01's already-tested `call_structured` retry wrapper directly
(no interim direct-call step) via `client_factory.get_client()`/
`client_factory.model_for()` accessed through the module (not imported by
name) so `tests/conftest.py`'s `mock_openai_parse` fixture — which
monkeypatches `algorunner.llm.client_factory.get_client` — takes effect
regardless of when this module was first imported. Mirrors the existing
`monkeypatch.setattr(<module>.asyncio, "sleep", ...)` convention already
established in `graph/build.py`/`worker/tasks.py`.
"""

from algorunner.agents.problem_analyzer.prompts import build_analysis_messages
from algorunner.config import settings
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.problem import ProblemAnalysis


async def problem_analyzer_node(state: GraphState) -> dict:
    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("problem_analyzer"),
        messages=build_analysis_messages(state),
        response_format=ProblemAnalysis,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Analyzer refused or failed to parse: {message.refusal}")
    analysis: ProblemAnalysis = message.parsed

    rounds = state.get("clarification_rounds", 0)
    assumption_text = state.get("assumption_stated")
    if analysis.needs_clarification and rounds >= settings.clarification_round_cap:
        # D-04: never pause past the round cap; proceed under a stated assumption.
        detail = analysis.clarification_question or "no further detail was available"
        analysis = analysis.model_copy(update={"needs_clarification": False})
        assumption_text = (
            f"Clarification could not be fully resolved after {rounds} round(s); "
            f"proceeding under the Analyzer's best interpretation: {detail}"
        )
    return {"analysis": analysis, "assumption_stated": assumption_text}
