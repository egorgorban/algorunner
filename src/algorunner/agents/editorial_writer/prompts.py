"""Prompt builder for the Editorial Writer agent.

Constructs the system and user messages for the LLM structured-output call,
ensuring code is never included and that all prose fields are instructed to be
in Russian.
"""

from algorunner.schemas.outcome import ApproachOutcome


def build_editorial_messages(
    state: dict,
    verified: list[ApproachOutcome],
    unverified: list[ApproachOutcome],
    retry_reason: str | None = None,
) -> list[dict]:
    """Build the LLM prompt messages for the Editorial Writer.

    System prompt instructs Russian prose, no code, and proper formatting.
    User message fences problem, analysis, and approach data as DATA blocks,
    never including Python or Go source code. On retry, a section names the
    failure reason (structural or language check).

    Args:
        state: The current graph state
        verified: List of verified ApproachOutcome objects
        unverified: List of unverified ApproachOutcome objects
        retry_reason: If set, appends a "Your previous draft was rejected because:" section (D-16)

    Returns:
        List of message dicts for the LLM
    """
    system_prompt = """You are an expert technical writer preparing a LeetCode-style editorial article.

Your task:
- Write every prose field in Russian, whatever the input language
- Wrap identifiers and variable names in backticks
- Never write code — code will be injected from verified solutions
- For each approach: intuition → algorithm → complexity with a ONE-line justification
- Choose the presentation order yourself (usually simplest to best)
- Role hints at an approach's place in the story (brute_force usually comes first) but is not a sort key
- For each approach after the first, write bridge_from_previous: one sentence explaining why it improves on the previous
- Copy each given Big-O notation exactly
- Use exactly the given verified approach ids
- Give each non-verified approach one short unverified note saying it was attempted but not verified, with no code
- notes and edge_cases may be empty lists"""

    # Build user message with DATA blocks
    problem_data = f"""PROBLEM TEXT:
{state['problem_text']}

ANALYSIS:
Intent: {state['analysis'].intent}
Constraints: {', '.join(state['analysis'].constraints) if state['analysis'].constraints else 'None'}
Difficulty: {state['analysis'].difficulty}

INPUT SHAPE: {state['analysis'].input_shape}
OUTPUT SHAPE: {state['analysis'].output_shape}

ASSUMPTIONS STATED: {state.get('assumption_stated') or 'None'}"""

    verified_data_parts = []
    for outcome in verified:
        verified_data_parts.append(
            f"""Approach ID {outcome.approach_idx}:
Name: {outcome.approach.name}
Technique: {outcome.approach.technique}
Role: {outcome.approach.role}
Rationale: {outcome.approach.rationale}
Summary: {outcome.approach.summary}
Algorithm: {outcome.final_solution.algorithm}
Complexity Time: {outcome.final_solution.complexity_time}
Complexity Space: {outcome.final_solution.complexity_space}
Review Complexity Reasoning: {outcome.final_review.complexity_reasoning if outcome.final_review else 'N/A'}"""
        )

    unverified_data_parts = []
    for outcome in unverified:
        unverified_data_parts.append(
            f"""Approach ID {outcome.approach_idx}:
Name: {outcome.approach.name}
Technique: {outcome.approach.technique}
Role: {outcome.approach.role}
Rationale: {outcome.approach.rationale}
Status: {outcome.status}"""
        )

    user_message = f"""{problem_data}

VERIFIED APPROACHES (all must appear in your output):
{chr(10).join(verified_data_parts)}"""

    if unverified:
        user_message += f"\n\nUNVERIFIED APPROACHES (include as brief mentions with status but no code):\n{chr(10).join(unverified_data_parts)}"

    # D-16: append retry reason if set
    if retry_reason:
        user_message += f"\n\n---\n\nYour previous draft was rejected because:\n```\n{retry_reason}\n```\n\nPlease revise the editorial to address this issue."

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
