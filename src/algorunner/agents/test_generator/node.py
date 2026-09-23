"""Test Generator graph node.

Merges `state["examples"]` (verbatim, never trusted to the LLM's echo —
D-10) with freshly LLM-generated test cases into `state["solution"].tests`.
Enforces D-11's numeric floor in code, not just via prompt instruction: when
fewer than 3 examples were provided, at least
`settings.test_generator_min_tests` generated tests are required, or a
`ValueError` is raised rather than silently shipping too few tests.
"""

from pydantic import BaseModel, Field

from algorunner.agents.test_generator.prompts import build_test_messages
from algorunner.config import settings
from algorunner.graph.state import GraphState
from algorunner.llm import client_factory
from algorunner.llm.retry import call_structured


class TestCase(BaseModel):
    input: str
    output: str


class GeneratedTests(BaseModel):
    tests: list[TestCase]


async def test_generator_node(state: GraphState) -> dict:
    completion = await call_structured(
        client_factory.get_client(),
        model=client_factory.model_for("test_generator"),
        messages=build_test_messages(state),
        response_format=GeneratedTests,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Test Generator refused or failed to parse: {message.refusal}")
    result = message.parsed

    # D-10: never trust the LLM to correctly echo provided examples back
    # verbatim — the merge is performed here, in Python.
    provided = [{"input": e["input"], "output": e["output"]} for e in state["examples"]]
    generated = [{"input": t.input, "output": t.output} for t in result.tests]

    # D-11: hard minimum of settings.test_generator_min_tests generated
    # tests when fewer than 3 examples were provided. Enforced in code, not
    # left to prompt-only guidance.
    if len(state["examples"]) < 3 and len(generated) < settings.test_generator_min_tests:
        raise ValueError(
            f"Test Generator produced only {len(generated)} tests, below the "
            f"required minimum of {settings.test_generator_min_tests} when "
            "fewer than 3 examples are provided"
        )

    merged = provided + generated
    return {"solution": state["solution"].model_copy(update={"tests": merged})}
