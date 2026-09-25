# Agents & Tools

## Overview

The pipeline consists of 7 LLM-backed agent nodes and 2 deterministic executor tools. Each node reads a subset of the graph state, calls an LLM with a structured prompt, validates the response via Pydantic, and writes structured output back to the state. Agents are wired into the LangGraph StateGraph and reuse a common checkpoint across all nodes.

## Agent Nodes

### Problem Analyzer

**Purpose:** Extract task intent, constraints, and difficulty from free-text problem input. When the problem is ambiguous or underspecified, emit a clarification question instead of guessing.

**State Read:** `problem_text`, `language`, `examples`, `clarification_answer`, `clarification_rounds`

**State Write:** `analysis` (ProblemAnalysis), `assumption_stated`, `clarification_rounds`, `clarifications`

**Output Schema:** `ProblemAnalysis`
- `problem_statement: str` — concise restatement
- `constraints: list[str]`
- `input_output_format: str`
- `difficulty: str` — "Easy", "Medium", or "Hard"
- `clarification_question: str | None`
- `interpretation: str` — explanation of interpretation if clarification was needed

**Model Config:** `problem_analyzer_model` (env var); falls back to `default_model`

### Solution Strategist

**Purpose:** Propose 1+ distinct solution approaches (e.g., brute-force, optimized, alternative). Each approach is tagged with its technique and given a rationale for inclusion.

**State Read:** `analysis`, `problem_text`, `examples`

**State Write:** `approaches` (list[Approach])

**Output Schema:** `list[Approach]`
- `approach_idx: int`
- `name: str` — "Brute-force", "Optimized", etc.
- `technique: str` — "Two pointers", "Dynamic programming", "Graph BFS", etc.
- `role: str` — Why this approach is useful (e.g., "baseline for comparison")

**Model Config:** `solution_strategist_model`; falls back to `default_model`

### Solver

**Purpose:** Elaborate a Strategist-proposed approach into a detailed algorithm. Solver is invoked once per approach in a parallel branch.

**State Read (per branch):** `approach`, `analysis`, `problem_text`, `examples`, `assumption_stated`

**State Write (per branch):** `solver_output` (Solution)

**Output Schema:** `Solution`
- `algorithm_description: str` — step-by-step explanation
- `pseudocode: str` — language-agnostic pseudocode or algorithm outline
- `complexity_analysis: str` — Big-O claim with a brief justification

**Model Config:** `solver_model`; falls back to `default_model`

### Code Generator

**Purpose:** Generate Python and Go implementations from the Solver's algorithm. One invocation per approach per language.

**State Read (per branch):** `solver_output`, `approach`, `examples`

**State Write (per branch):** `python_code` (str), `go_code` (str)

**Output Schema:** Dictionary with `python_code` and `go_code` string keys

**Model Config:** `code_generator_model`; falls back to `default_model`

### Test Generator

**Purpose:** Produce test cases for the approach. Incorporates provided examples and generates additional edge-case tests to reach a minimum count (10 by default).

**State Read (per branch):** `approach`, `solver_output`, `examples`, `problem_text`

**State Write (per branch):** `tests` (list[str])

**Output Schema:** `list[GeneratedTest]`
- `input_data: dict | list` — serializable test input
- `expected_output: dict | list` — expected output
- `description: str` — "Example provided", "Edge case: negative", etc.

**Model Config:** `test_generator_model`; falls back to `default_model`

### Reviewer

**Purpose:** Evaluate each approach's correctness, algorithm soundness, edge-case coverage, and complexity claim. Returns a structured ReviewResult indicating pass/fail and any required corrections.

**State Read (per branch):** `python_execution`, `go_execution`, `approach`, `solver_output`, `tests`

**State Write (per branch):** `review` (ReviewResult), `review_history` (list)

**Output Schema:** `ReviewResult`
- `passed: bool`
- `issues: list[str]` — problems identified
- `severity: str` — "error" (blocks pass), "warning" (noted but pass acceptable)
- `required_changes: str` — instructions for correction if issues present
- `edge_cases_handled: list[str]` — edge cases the reviewer verified are covered

**Model Config:** `reviewer_model`; falls back to `default_model`

### Editorial Writer

**Purpose:** Compose the final Russian-language editorial article. Triggered once all approaches complete (at least one verified). Assembles the editorial from all verified approaches into a structured JSON object.

**State Read:** `analysis`, `approaches`, `approach_outcomes`, `editorial_warnings`

**State Write:** `editorial` (Editorial)

**Output Schema:** `Editorial`
- `title: str` — Problem title in Russian
- `problem_statement: str` — Problem restatement in Russian (incorporates clarification if applicable)
- `difficulty: str` — Difficulty rating from Analyzer
- `techniques: list[str]` — Topic tags from approaches
- `editorial_approaches: list[EditorialApproach]` — one per verified approach
  - `name: str`
  - `technique: str`
  - `intuition: str` — Why this approach works
  - `algorithm: str` — Step-by-step explanation
  - `python_code: str` — Verbatim from Code Generator
  - `go_code: str` — Verbatim from Code Generator
  - `complexity: str` — Time + space with justification (from Solver)
  - `edge_cases: list[str]` — From Reviewer
- `notes: str` — Additional context, bridges between approaches

**Model Config:** No dedicated `editorial_writer_model` field; falls back to `default_model` via the default lookup in `model_for()`

## Executor Tools

### Python Executor

**Purpose:** Run generated Python code against test cases in a deterministic, non-LLM tool.

**Input:** Python source code (str), list of test cases (serialized as JSON)

**Output:** `ExecutionResult`
- `passed: bool` — all tests passed
- `test_results: list[dict]` — per-test status (passed/failed, expected vs actual, error message)
- `execution_time_ms: float`
- `error_summary: str` — if execution crashed before all tests

**Implementation:** `subprocess.Popen`, `preexec_fn` for uid 65534 + resource limits, import denylist enforcer

### Go Executor

**Purpose:** Compile and run generated Go code against test cases.

**Input:** Go source code (str), Go test harness, list of test cases

**Output:** `ExecutionResult` (same shape as Python)

**Implementation:** Docker container with Go toolchain; compile to binary, run with `subprocess.Popen`, uid 65534, resource limits

## Adding an Agent

1. **Define the Pydantic schema** in `src/algorunner/schemas/` (e.g., `schemas/my_schema.py`).
2. **Create the agent module** at `src/algorunner/agents/{agent_name}/`:
   - `node.py` — async node function `async def {agent_name}_node(state: GraphState, runtime: Runtime[PipelineContext]) -> dict:`
   - `prompts.py` — prompt templates and system instructions
3. **Wire into the graph** in `src/algorunner/graph/build.py` or `src/algorunner/graph/approach.py`:
   - Add an edge from the prior node to the new node
   - Specify state keys passed to the node
4. **Set up model config** in `src/algorunner/config.py`:
   - Add `{agent_name}_model: str | None = None` field
   - Defaults to `default_model` if not overridden
5. **Test with mock dispatcher** in `tests/`:
   - Create a test using the `mock_pipeline_openai` fixture
   - Mock the OpenAI response for your schema
   - Verify the node returns the correct state update

Example test structure:
```python
async def test_my_agent_node(mock_pipeline_openai):
    state = GraphState(task_id="...", ...)
    result = await my_agent_node(state, mock_runtime)
    assert result["output_field"] == expected_value
```

## Model Configuration

Each agent reads its own `*_model` environment variable. If unset, `model_for()` in `llm/client_factory.py` returns `default_model`.

```python
# config.py
default_model: str = "gpt-4o-mini"
problem_analyzer_model: str | None = None
solution_strategist_model: str | None = None
solver_model: str | None = None
code_generator_model: str | None = None
test_generator_model: str | None = None
reviewer_model: str | None = None
# No editorial_writer_model — uses default_model
```

Use case: set `SOLVER_MODEL=gpt-4o` for stronger reasoning while keeping cheaper models for analysis/review.
