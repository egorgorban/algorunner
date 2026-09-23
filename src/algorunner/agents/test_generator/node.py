"""Test Generator graph node.

Produces `state["solution"].tests` as language-neutral `StructuredCase`s typed
against the Code Generator's entry point (CODE-03/04).

- D-10: every provided example is present first, in original order, with
  origin "provided". Deterministic parsing wins where it succeeds; examples it
  cannot parse are normalized by this node's single LLM call and verified in
  Python. The merge is performed here, never trusted to the LLM.
- D-11: when fewer than 3 examples were provided, at least
  `settings.test_generator_min_tests` generated cases are required, enforced
  in code (ValueError), not just in the prompt.
- D-12: each generated case carries a label saying what it covers.
- D-00f: an invalid generated case raises ValueError naming the case; nothing
  is silently dropped or coerced.
"""

from pydantic import BaseModel, Field

from algorunner.agents.test_generator.prompts import build_test_messages
from algorunner.config import settings
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured
from algorunner.schemas.example_cases import build_normalized_example, parse_provided_example
from algorunner.schemas.solution import StructuredCase
from algorunner.schemas.typespec import MAX_CASES, parse_json_text


class TestCase(BaseModel):
    label: str = Field(..., min_length=1)
    args_json: str
    expected_json: str


class NormalizedExample(BaseModel):
    example_index: int
    args_json: str
    expected_json: str


class GeneratedTests(BaseModel):
    tests: list[TestCase]
    normalized_examples: list[NormalizedExample]


async def test_generator_node(state: GraphState) -> dict:
    solution = state["solution"]
    entry_point = solution.entry_point

    provided_by_index: dict[int, StructuredCase] = {}
    pending: list[tuple[int, dict]] = []
    for index, example in enumerate(state["examples"]):
        case = parse_provided_example(
            entry_point,
            index=index,
            input_text=example["input"],
            output_text=example["output"],
        )
        if case is not None:
            provided_by_index[index] = case
        else:
            pending.append((index, example))

    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("test_generator"),
        messages=build_test_messages(state, pending),
        response_format=GeneratedTests,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Test Generator refused or failed to parse: {message.refusal}")
    result = message.parsed

    # Normalized examples must cover exactly the pending indices, once each.
    pending_indices = {index for index, _ in pending}
    seen: set[int] = set()
    for normalized in result.normalized_examples:
        if normalized.example_index not in pending_indices:
            raise ValueError(
                f"Test Generator normalized unknown example index {normalized.example_index}"
            )
        if normalized.example_index in seen:
            raise ValueError(
                f"Test Generator normalized example index {normalized.example_index} twice"
            )
        seen.add(normalized.example_index)
    missing = sorted(pending_indices - seen)
    if missing:
        raise ValueError(f"Test Generator did not normalize example indices {missing}")
    examples = state["examples"]
    for normalized in result.normalized_examples:
        provided_by_index[normalized.example_index] = build_normalized_example(
            entry_point,
            index=normalized.example_index,
            output_text=examples[normalized.example_index]["output"],
            args_json=normalized.args_json,
            expected_json=normalized.expected_json,
        )

    generated: list[StructuredCase] = []
    for position, test in enumerate(result.tests):
        try:
            generated.append(
                entry_point.make_case(
                    label=test.label,
                    origin="generated",
                    args=parse_json_text(test.args_json),  # type: ignore[arg-type]
                    expected=parse_json_text(test.expected_json),  # type: ignore[arg-type]
                )
            )
        except ValueError as exc:
            raise ValueError(
                f"generated test case {position} ({test.label}) is invalid: {exc}"
            ) from exc

    # D-11: hard minimum of settings.test_generator_min_tests generated
    # tests when fewer than 3 examples were provided.
    if len(state["examples"]) < 3 and len(generated) < settings.test_generator_min_tests:
        raise ValueError(
            f"Test Generator produced only {len(generated)} tests, below the "
            f"required minimum of {settings.test_generator_min_tests} when "
            "fewer than 3 examples are provided"
        )

    # D-10: provided cases first, in original example order.
    provided = [provided_by_index[i] for i in range(len(state["examples"]))]
    merged = provided + generated
    if len(merged) > MAX_CASES:
        raise ValueError(f"{len(merged)} test cases exceed the maximum of {MAX_CASES}")
    return {"solution": solution.model_copy(update={"tests": merged})}
