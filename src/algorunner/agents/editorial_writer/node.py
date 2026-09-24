"""Editorial Writer agent node — assembles verified approaches into a Russian-prose Editorial.

Calls the LLM once with structured output, validating the response and injecting
deterministic metadata (code, Big-O, difficulty, tags, role).
"""

from algorunner.agents.editorial_writer.assembly import assemble_editorial
from algorunner.agents.editorial_writer.prompts import build_editorial_messages
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.editorial import Editorial, EditorialDraft


async def editorial_writer_node(state: dict) -> dict:
    """Compose verified approaches into the editorial.

    Calls the Editorial Writer LLM with structured output, then deterministically
    injects code (byte-for-byte from executed Solutions), Big-O, difficulty, tags
    and role into the draft.

    Args:
        state: Graph state dict with problem_text, analysis, assumption_stated,
               and approach_outcomes (dict of approach_idx -> ApproachOutcome)

    Returns:
        {"editorial": Editorial} with all fields populated

    Raises:
        ValueError: if the LLM refuses, if no approaches are verified, or if
                   the assembled editorial is structurally invalid
    """
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

    response = await call_structured(
        client,
        model=model,
        messages=messages,
        response_format=EditorialDraft,
    )

    # Check for refusal
    if response.choices[0].message.parsed is None:
        raise ValueError(
            f"Editorial Writer refused or failed to parse: {response.choices[0].message.refusal}"
        )

    draft = response.choices[0].message.parsed

    # Assemble the editorial with injected metadata
    editorial = assemble_editorial(draft, state["analysis"], outcomes)

    return {"editorial": editorial}
