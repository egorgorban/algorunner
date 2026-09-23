"""Subprocess-based `CodeExecutor` for generated Python code (EXEC-01).

Follows RESEARCH.md Pattern 3 (verified against `asyncio.create_subprocess_exec`'s
documented `Popen` kwarg pass-through) with the mandatory additions this
plan's `<action>` calls out beyond the base template:

- a static AST-based import denylist checked BEFORE any subprocess spawns
- `_PYTHON_LIMITS` (via `tools.process.make_limit_fn`) — CPU/address-space/process-count caps, deliberately
  NOT the file-size-zero limit CLAUDE.md's "What NOT to Use" section warns
  against (SIGXFSZ on any file write, including inherited stderr, produces
  confusing false "crashes")
- a minimal, non-inherited subprocess environment (T-02-05-02: generated
  code must never read `OPENAI_API_KEY`/`DATABASE_URL`/`REDIS_URL` via
  `os.environ`, even if the denylist is somehow bypassed)
- whole-process-group kill on every exit path (timeout AND cancellation),
  owned by `tools.process.run_in_process_group`

`tests` is literal source appended directly after `code` (matching Pattern
3's `script.write_text(code + "\\n\\n" + tests)` exactly) — e.g. a sequence
of `assert` statements. A failed `assert` raises `AssertionError`, which
Python's default excepthook prints to stderr and exits non-zero on its own;
no separate pass/fail protocol is needed.
"""

import ast
import os
import tempfile
import time
from pathlib import Path

from algorunner.schemas.execution import ExecutionResult
from algorunner.tools.process import make_limit_fn, run_in_process_group

_DENYLISTED_IMPORTS = {
    "os",
    "subprocess",
    "socket",
    "shutil",
    "sys",
    "ctypes",
    "multiprocessing",
    "threading",
}


def _check_denylist(code: str) -> str | None:
    """Returns the first disallowed top-level module name imported by
    `code`, or `None` if clean. Matches the top-level module for dotted
    imports too (e.g. `os.path` still matches `os`)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # A syntax error in generated code is a real-execution concern, not
        # a denylist concern — let it through to the subprocess, which will
        # fail with a non-zero exit code and a SyntaxError on stderr.
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                if top_level in _DENYLISTED_IMPORTS:
                    return top_level
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                top_level = node.module.split(".")[0]
                if top_level in _DENYLISTED_IMPORTS:
                    return top_level
    return None


# CPU/address-space/process-count caps. RLIMIT_NPROC=0 blocks fork() (no fork
# bombs); no file-size limit is set (see `make_limit_fn`).
_PYTHON_LIMITS = make_limit_fn(
    cpu_s=5,
    address_space_bytes=512 * 1024 * 1024,
    open_files=256,
    max_processes=0,
)


class SubprocessPythonExecutor:
    """`CodeExecutor` implementation running generated Python via
    `asyncio.create_subprocess_exec` (never blocking `subprocess.run` —
    CLAUDE.md "What NOT to Use")."""

    async def run(
        self, code: str, tests: str, *, timeout_s: float = 10.0
    ) -> ExecutionResult:
        disallowed = _check_denylist(code)
        if disallowed is not None:
            return ExecutionResult(
                passed=False,
                stdout="",
                stderr=f"Disallowed import: {disallowed}",
                exit_code=-1,
                duration_ms=0,
            )

        started = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "solution.py"
            script.write_text(code + "\n\n" + tests)

            out = await run_in_process_group(
                ["python3", str(script)],
                cwd=tmp,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                timeout_s=timeout_s,
                limit_fn=_PYTHON_LIMITS,
            )
            if out is None:
                return ExecutionResult(
                    passed=False,
                    stdout="",
                    stderr="timed out",
                    exit_code=-1,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            stdout, stderr, returncode = out

            duration_ms = int((time.monotonic() - started) * 1000)
            return ExecutionResult(
                passed=returncode == 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=returncode,
                duration_ms=duration_ms,
            )
