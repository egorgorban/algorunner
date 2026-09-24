"""Editorial Writer agent node — assembles verified approaches into a Russian-prose Editorial.

Calls the LLM up to twice with structured output (D-16: one retry on failure), validating
the response and injecting deterministic metadata (code, Big-O, difficulty, tags, role).

Per the user-confirmed decision (2026-09-24, D-16): structural failures fail the task with
EDITORIAL_ASSEMBLY_FAILED; language failures ship the editorial with editorial_warnings.
"""

import asyncio
import logging

from langgraph.runtime import Runtime

from algorunner.agents.editorial_writer.assembly import assemble_editorial
from algorunner.agents.editorial_writer.language import check_russian, prose_fields
from algorunner.agents.editorial_writer.prompts import build_editorial_messages
from algorunner.config import settings
from algorunner.graph.context import PipelineContext, emit_status, remaining_s
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.editorial import Editorial, EditorialDraft
from algorunner.schemas.task import TaskStatus

logger = logging.getLogger(__name__)


def soft_warnings(draft: EditorialDraft, verified: list = None) -> list[str]:
    """Check for soft (non-structural) failures and return warning codes.

    In Plan 03-06, returns ["language_check_failed"] when the draft fails the
    Russian-language check. Plan 03-07 extends this with completeness checks
    for edge cases and notes.

    Args:
        draft: The EditorialDraft from the LLM
        verified: List of verified ApproachOutcome objects (for edge cases/notes checks)

    Returns:
        List of warning codes (empty if all soft checks pass)
    """
    warnings = []

    # Language check: if the prose fails Russian-language thresholds, return warning
    fields = prose_fields(draft)
    if not check_russian(
        fields,
        aggregate_min=settings.editorial_cyrillic_min_ratio,
        field_min=settings.editorial_cyrillic_field_min_ratio,
    ):
        warnings.append("language_check_failed")

    # EDIT-05: Check for edge cases completeness
    # If any verified approach has handled_edge_cases and draft.edge_cases is empty, warn
    if verified:
        has_handled_edge_cases = any(
            outcome.final_review and outcome.final_review.handled_edge_cases
            for outcome in verified
        )
        if has_handled_edge_cases and not draft.edge_cases:
            warnings.append("edge_cases_missing")

        # Check for notes completeness
        # If any verified approach has a minor issue but draft notes are empty for that approach, warn
        for outcome in verified:
            if outcome.final_review and outcome.final_review.issues:
                has_minor_issue = any(
                    issue.severity == "minor"
                    for issue in outcome.final_review.issues
                )
                if has_minor_issue:
                    # Find the draft approach with this approach_id
                    draft_approach = None
                    for draft_app in draft.approaches:
                        if draft_app.approach_id == outcome.approach_idx:
                            draft_approach = draft_app
                            break

                    if draft_approach and not draft_approach.notes:
                        warnings.append("notes_missing")
                        break  # Only warn once for notes_missing

    return warnings


async def editorial_writer_node(state: dict, runtime: Runtime[PipelineContext]) -> dict:
    """Compose verified approaches into the editorial with one-retry on failure (D-16).

    Calls the Editorial Writer LLM with structured output (per-attempt timeout),
    then deterministically injects code (byte-for-byte from executed Solutions),
    Big-O, difficulty, tags and role into the draft.

    D-16 retry-once (user-confirmed 2026-09-24):
    - Call 1: LLM draft. On failure, name the reason and retry once.
    - Call 2: Retry with failure reason in the prompt.
    - Outcome split by failure type:
      * Structural (approach IDs don't match, bridge rules broken): fail task with EDITORIAL_ASSEMBLY_FAILED
      * Language (Russian check fails): ship the verified draft with editorial_warnings=["language_check_failed"]
    - Refusal (parsed None) raises immediately after the first call (D-00f).

    Emits WRITING_EDITORIAL status before the LLM calls. Each call is bounded by
    settings.editorial_attempt_timeout_s. When remaining_s(context) is set, the
    entire node is also bounded by the global invocation deadline.

    Args:
        state: Graph state dict with problem_text, analysis, assumption_stated,
               and approach_outcomes (dict of approach_idx -> ApproachOutcome)
        runtime: LangGraph Runtime to access PipelineContext with deadline and status_sink

    Returns:
        {"editorial": Editorial, "editorial_warnings": [...]} on success with soft checks passing.
        {"editorial": Editorial, "editorial_warnings": ["language_check_failed"]} if language check fails after retry.
        {"error": {"code": "EDITORIAL_ASSEMBLY_FAILED", ...}} if structural checks fail after retry.

    Raises:
        ValueError: if the LLM refuses on attempt 1, or no approaches are verified
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

    client = client_factory.get_client()
    model = client_factory.model_for("editorial_writer")

    # Compute per-attempt timeout
    attempt_timeout = settings.editorial_attempt_timeout_s
    remaining = remaining_s(ctx)
    if remaining is not None and remaining > 0:
        timeout = min(attempt_timeout, max(1.0, remaining))
    else:
        timeout = attempt_timeout

    # Helper: make the LLM call with timeout
    async def call_writer(retry_reason: str | None = None):
        messages = build_editorial_messages(state, verified, unverified, retry_reason=retry_reason)

        async def call_with_timeout():
            return await call_structured(
                client,
                model=model,
                messages=messages,
                response_format=EditorialDraft,
                timeout=timeout,
            )

        if remaining is not None and remaining > 0:
            return await asyncio.wait_for(call_with_timeout(), timeout=max(1.0, remaining))
        else:
            return await call_with_timeout()

    # Attempt 1: initial call
    response = await call_writer()

    # Check for refusal (D-00f: not retried)
    if response.choices[0].message.parsed is None:
        raise ValueError(
            f"Editorial Writer refused or failed to parse: {response.choices[0].message.refusal}"
        )

    draft1 = response.choices[0].message.parsed

    # Try to assemble attempt 1
    assembly_error1: str | None = None
    editorial1: Editorial | None = None
    try:
        editorial1 = assemble_editorial(draft1, state["analysis"], outcomes)
    except ValueError as e:
        assembly_error1 = str(e)

    # Check soft failures on attempt 1
    warnings1 = soft_warnings(draft1, verified) if editorial1 else []

    # If attempt 1 has no failures, return it
    if editorial1 is not None and not warnings1:
        return {"editorial": editorial1, "editorial_warnings": []}

    # Determine retry reason: structural failure or soft failure
    if assembly_error1:
        retry_reason = f"structural error: {assembly_error1[:100]}"
    elif warnings1:
        retry_reason = f"language check failed: Russian prose ratio below threshold"
    else:
        # Shouldn't happen, but handle gracefully
        retry_reason = "quality check failed, please retry"

    # Attempt 2: retry with reason
    response = await call_writer(retry_reason=retry_reason)

    # Check for refusal on attempt 2 (also not retried)
    if response.choices[0].message.parsed is None:
        raise ValueError(
            f"Editorial Writer refused on retry or failed to parse: {response.choices[0].message.refusal}"
        )

    draft2 = response.choices[0].message.parsed

    # Try to assemble attempt 2
    assembly_error2: str | None = None
    editorial2: Editorial | None = None
    try:
        editorial2 = assemble_editorial(draft2, state["analysis"], outcomes)
    except ValueError as e:
        assembly_error2 = str(e)

    # Check soft failures on attempt 2
    warnings2 = soft_warnings(draft2, verified) if editorial2 else []

    # Decision logic per user-confirmed split:
    # 1. If attempt 2 assembled and has no hard failures: return it with warnings
    # 2. If attempt 2 has hard failure but attempt 1 assembled: return attempt 1 with warnings
    # 3. If both have hard failures: fail the task with EDITORIAL_ASSEMBLY_FAILED

    if editorial2 is not None:
        # Attempt 2 assembled
        if warnings2:
            logger.warning(f"Editorial Writer attempt 2: shipping with warnings: {warnings2}")
        return {"editorial": editorial2, "editorial_warnings": warnings2}

    if editorial1 is not None:
        # Attempt 2 failed to assemble, but attempt 1 did
        if warnings1:
            logger.warning(f"Editorial Writer attempt 1: shipping with warnings: {warnings1}")
        return {"editorial": editorial1, "editorial_warnings": warnings1}

    # Both attempts failed to assemble (structural failure on both)
    error_msg = f"attempt 1: {assembly_error1}; attempt 2: {assembly_error2}".replace("\n", " ")
    if len(error_msg) > 500:
        error_msg = error_msg[:500]

    return {
        "error": {
            "code": "EDITORIAL_ASSEMBLY_FAILED",
            "message": error_msg,
        }
    }
