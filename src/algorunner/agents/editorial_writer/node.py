"""Editorial Writer agent node — assembles verified approaches into a Russian-prose Editorial.

Calls the LLM once with structured output (bounded by per-attempt timeout), validating
the response and injecting deterministic metadata (code, Big-O, difficulty, tags, role).
"""

import asyncio

from langgraph.runtime import Runtime

from algorunner.agents.editorial_writer.assembly import assemble_editorial
from algorunner.agents.editorial_writer.prompts import build_editorial_messages
from algorunner.config import settings
from algorunner.graph.context import PipelineContext, emit_status, remaining_s
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.editorial import Editorial, EditorialDraft
from algorunner.schemas.task import TaskStatus


async def editorial_writer_node(state: dict, runtime: Runtime[PipelineContext]) -> dict:
    """Compose verified approaches into the editorial (D-10, ORCH-03, Pattern 10).

    Calls the Editorial Writer LLM with structured output (per-attempt timeout),
    then deterministically injects code (byte-for-byte from executed Solutions),
    Big-O, difficulty, tags and role into the draft.

    Emits WRITING_EDITORIAL status before the LLM call. The call itself is bounded by
    settings.editorial_attempt_timeout_s (per attempt, Plan 03-06 adds retry).

    When remaining_s(context) is set, the entire node is also bounded by the global
    invocation deadline (the LLM call timeout is min(attempt_timeout, remaining)).

    Args:
        state: Graph state dict with problem_text, analysis, assumption_stated,
               and approach_outcomes (dict of approach_idx -> ApproachOutcome)
        runtime: LangGraph Runtime to access PipelineContext with deadline and status_sink

    Returns:
        {"editorial": Editorial} with all fields populated

    Raises:
        ValueError: if the LLM refuses, if no approaches are verified, or if
                   the assembled editorial is structurally invalid
        asyncio.TimeoutError: if the invocation deadline passes before completion
    """
    ctx = runtime.context

    # Emit WRITING_EDITORIAL status (Pattern 11: logged, never raises)
    await emit_status(ctx, state["task_id"], TaskStatus.WRITING_EDITORIAL)

    # Separate verified and unverified outcomes
    outcomes = state.get("approach_outcomes", {})
    verified = [o for o in outcomes.values() if o.status == "verified"]
    unverified = [o for o in outcomes.values() if o.status != "verified"]

    if not verified:
        raise ValueError("Editorial Writer called with no verified approaches")

    # Build the prompt
    messages = build_editorial_messages(state, verified, unverified)

    # Call the LLM with structured output
    client = client_factory.get_client()
    model = client_factory.model_for("editorial_writer")

    # Compute the timeout for this attempt: per-attempt timeout, bounded by remaining
    attempt_timeout = settings.editorial_attempt_timeout_s
    remaining = remaining_s(ctx)
    if remaining is not None and remaining > 0:
        timeout = min(attempt_timeout, max(1.0, remaining))
    else:
        timeout = attempt_timeout

    # Call the structured LLM with timeout passed through to parse()
    async def call_with_timeout() -> dict:
        return await call_structured(
            client,
            model=model,
            messages=messages,
            response_format=EditorialDraft,
            timeout=timeout,
        )

    # Wrap in asyncio.wait_for if remaining deadline is set (double boundary)
    if remaining is not None and remaining > 0:
        response = await asyncio.wait_for(call_with_timeout(), timeout=max(1.0, remaining))
    else:
        response = await call_with_timeout()

    # Check for refusal
    if response.choices[0].message.parsed is None:
        raise ValueError(
            f"Editorial Writer refused or failed to parse: {response.choices[0].message.refusal}"
        )

    draft = response.choices[0].message.parsed

    # Assemble the editorial with injected metadata
    editorial = assemble_editorial(draft, state["analysis"], outcomes)

    return {"editorial": editorial}
