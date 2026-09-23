"""CodeExecutor Protocol — the swap surface between graph/agent code and the
concrete Python/Go execution backends.

Deterministic execution lives behind tools, not agents (PROJECT.md Key
Decisions: "Deterministic execution as tools, not agents (PythonExecutorTool,
GoExecutorTool) ... Keeps agent logic swappable from subprocess -> sandbox ->
isolated service later without touching agent code"). `SubprocessPythonExecutor`
and `SubprocessGoExecutor` are the only two implementations in v1; both
satisfy this single `run(...)` signature so graph/build.py never needs to
know which concrete backend it is calling (EXEC-03).
"""

from typing import Protocol

from algorunner.schemas.execution import ExecutionResult


class CodeExecutor(Protocol):
    async def run(
        self, code: str, tests: str, *, timeout_s: float = 10.0
    ) -> ExecutionResult: ...
