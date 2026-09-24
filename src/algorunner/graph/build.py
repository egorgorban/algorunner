"""Parent graph for Phase 3 multi-approach editorial pipeline (D-08, D-13).

The Phase 2 linear single-solution pipeline becomes a parent graph that fans
out to one per-approach branch after the Strategist, joins once all branches
complete, and routes to success or failure finalizers.

Each branch executes the Phase 2 pipeline (Solver through Reviewer) independently
on ApproachState. Branches are dispatched via `Send` and collected via a plain
edge to `collect_approaches`, then routed through `decide_after_join`.

The parent graph uses the injected-checkpointer convention (never constructed
here, only wired in by worker/tasks.py). Branch subgraphs inherit the parent's
checkpointer and have no checkpointer of their own.

finalize_success and finalize_failed return the new per-approach result shape
(D-13 approaches index) and the new error precedence (Pattern 12). Pre-Phase-3
completed rows retain the old result shape; Phase 4 UI must tolerate a missing
result.editorial.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from algorunner.agents.editorial_writer.node import editorial_writer_node
from algorunner.agents.problem_analyzer.node import problem_analyzer_node
from algorunner.agents.solution_strategist.node import solution_strategist_node
from algorunner.graph.approach import decide_after_join, fan_out_approaches
from algorunner.graph.context import PipelineContext, emit_status
from algorunner.graph.routing import decide_after_analysis, decide_after_writer
from algorunner.graph.state import GraphState
from algorunner.schemas.execution import ExecutionResult
from algorunner.schemas.task import TaskStatus


async def record_analysis_node(state: GraphState, runtime: Runtime[PipelineContext]) -> dict:
    """Emit DESIGNING_SOLUTION status after analysis completes (D-10, Pattern 11).

    This zero-logic node marks the transition from problem analysis to solution
    design. It provides a natural checkpoint for status tracking (designing_solution
    status in Postgres) before branching to strategy and execution.

    Plan 03-08 will add artifact persistence (writing analysis to Garage) to this node.
    """
    ctx = runtime.context
    await emit_status(ctx, state["task_id"], TaskStatus.DESIGNING_SOLUTION)
    return {}


async def clarification_gate_node(state: GraphState) -> dict:
    """Zero-logic on purpose: on resume only this trivial node re-executes,
    never the Analyzer's LLM call (RESEARCH Pattern 2)."""
    answer = interrupt(state["analysis"].clarification_question)
    return {
        "clarification_answer": answer,
        "clarification_rounds": state["clarification_rounds"] + 1,
    }


async def collect_approaches(state: GraphState) -> dict:
    """Fan-in join: collect all approach branches (zero logic).

    This is a no-op node whose sole purpose is to collect Send results
    from all branches into the parent state's approach_outcomes dict via
    the merge_outcomes reducer.
    """
    return {}


async def finalize_success(state: GraphState) -> dict:
    """Write the final result dict for a successfully completed run.

    Result shape (D-13 approaches index, D-11 editorial):
    - approaches: array of {approach_id, name, technique, role, status, iterations}
      in ascending approach_id order
    - editorial: structured Editorial JSON (filled by editorial_writer_node)
    - editorial_warnings: list of warning codes from deterministic checks (Plan 03-06)

    Pre-Phase-3 completed rows keep the old shape with per-solution keys.
    """
    outcomes = state.get("approach_outcomes", {})
    approaches_index = [
        {
            "approach_id": idx,
            "name": outcome.approach.name,
            "technique": outcome.approach.technique,
            "role": outcome.approach.role,
            "status": outcome.status,
            "iterations": outcome.iterations,
        }
        for idx, outcome in sorted(outcomes.items())
    ]
    result = {
        "approaches": approaches_index,
    }
    if state.get("editorial"):
        result["editorial"] = state["editorial"].model_dump()
    # D-16: editorial_warnings is always present (empty list if all checks pass)
    result["editorial_warnings"] = state.get("editorial_warnings", [])
    return {"result": result}


async def finalize_failed(state: GraphState) -> dict:
    """Terminal FAILED result when zero approaches are verified.

    Precedence (RESEARCH Pattern 12, D-06):
    1. CORRECTION_LOOP_EXHAUSTED if any outcome is "exhausted"
    2. GLOBAL_TIMEOUT if any outcome is "timed_out"
    3. APPROACH_PIPELINE_ERROR otherwise (exception in a branch)

    Message format: "0 of N approaches verified: #idx name=status (k iterations) ... "

    result stays None (D-13, RESEARCH Open Q2).
    """
    outcomes = state.get("approach_outcomes", {})

    # Determine error code via precedence
    any_exhausted = any(o.status == "exhausted" for o in outcomes.values())
    any_timed_out = any(o.status == "timed_out" for o in outcomes.values())

    if any_exhausted:
        code = "CORRECTION_LOOP_EXHAUSTED"
    elif any_timed_out:
        code = "GLOBAL_TIMEOUT"
    else:
        code = "APPROACH_PIPELINE_ERROR"

    # Build message: count approaches and detail each
    n_approaches = len(outcomes)
    message_lines = [f"0 of {n_approaches} approaches verified:"]

    for idx, outcome in sorted(outcomes.items()):
        status_part = f"#{idx} {outcome.approach.name}={outcome.status} ({outcome.iterations} iterations)"
        message_lines.append(status_part)

    # For APPROACH_PIPELINE_ERROR, append the first error's details
    if code == "APPROACH_PIPELINE_ERROR":
        for outcome in sorted(outcomes.values(), key=lambda o: o.approach_idx):
            if outcome.error:
                message_lines.append(outcome.error)
                break

    return {
        "error": {
            "code": code,
            "message": " ".join(message_lines),
        }
    }


def build_pipeline_graph(checkpointer: object) -> CompiledStateGraph:
    """Build the parent graph with Send fan-out to per-approach branches.

    Nodes:
    - analyzer: Problem analysis (unchanged from Phase 2)
    - record_analysis: Emit DESIGNING_SOLUTION status (D-10, Pattern 11)
    - clarification_gate: Pause/resume (unchanged)
    - strategist: Approach selection (unchanged; will be updated in 03-03 for curation)
    - run_approach: Dispatch to per-approach subgraph (via Send from fan_out_approaches)
    - collect_approaches: Join point for all branches (zero logic)
    - editorial_writer: Compose verified approaches into Editorial (Phase 03-04)
    - finalize_success: Write result with approaches and editorial on verified outcome
    - finalize_failed: Write error with precedence on zero-verified outcome

    Edges:
    - START -> analyzer
    - analyzer -> {clarification_gate, record_analysis} (decide_after_analysis)
    - clarification_gate -> analyzer
    - record_analysis -> strategist
    - strategist -> run_approach (via Send fan-out)
    - run_approach -> collect_approaches (plain edge)
    - collect_approaches -> {editorial_writer, finalize_failed} (decide_after_join)
    - editorial_writer -> finalize_success (plain edge)
    - finalize_success -> END
    - finalize_failed -> END

    Has context_schema=PipelineContext to receive runtime context with deadline and status_sink.
    """
    builder = StateGraph(GraphState, context_schema=PipelineContext)
    builder.add_node("analyzer", problem_analyzer_node)
    builder.add_node("record_analysis", record_analysis_node)
    builder.add_node("clarification_gate", clarification_gate_node)
    builder.add_node("strategist", solution_strategist_node)

    # Import here to avoid circular import (build.py imports approach.py, which imports routing.py)
    from algorunner.graph.approach import run_approach

    builder.add_node("run_approach", run_approach, input_schema=dict)
    builder.add_node("collect_approaches", collect_approaches)
    builder.add_node("editorial_writer", editorial_writer_node)
    builder.add_node("finalize_success", finalize_success)
    builder.add_node("finalize_failed", finalize_failed)

    builder.add_edge(START, "analyzer")
    builder.add_conditional_edges(
        "analyzer",
        decide_after_analysis,
        {"clarification_gate": "clarification_gate", "record_analysis": "record_analysis"},
    )
    builder.add_edge("clarification_gate", "analyzer")
    builder.add_edge("record_analysis", "strategist")

    # Fan-out: strategist -> one Send per approach to run_approach
    builder.add_conditional_edges(
        "strategist",
        fan_out_approaches,
        ["run_approach"],
    )

    # Plain edge: all Send results are merged into approach_outcomes via the reducer
    builder.add_edge("run_approach", "collect_approaches")

    # Fan-in router: route to editorial_writer (if verified) or finalize_failed
    builder.add_conditional_edges(
        "collect_approaches",
        decide_after_join,
        {"editorial_writer": "editorial_writer", "finalize_failed": "finalize_failed"},
    )

    # Editorial writer routes via decide_after_writer (D-16: split on failure type)
    builder.add_conditional_edges(
        "editorial_writer",
        decide_after_writer,
        {"finalize_success": "finalize_success", "end": END},
    )

    builder.add_edge("finalize_success", END)
    builder.add_edge("finalize_failed", END)

    return builder.compile(checkpointer=checkpointer)
