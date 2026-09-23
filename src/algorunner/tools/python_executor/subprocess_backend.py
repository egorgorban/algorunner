"""Subprocess-based `CodeExecutor` for generated Python code (EXEC-01).

Follows RESEARCH.md Pattern 3 (verified against `asyncio.create_subprocess_exec`'s
documented `Popen` kwarg pass-through) with the mandatory additions this
plan's `<action>` calls out beyond the base template:

- a static AST-based import denylist checked BEFORE any subprocess spawns
- `_limit_resources()` — CPU/address-space/process-count caps, deliberately
  NOT the file-size-zero limit CLAUDE.md's "What NOT to Use" section warns
  against (SIGXFSZ on any file write, including inherited stderr, produces
  confusing false "crashes")
- a minimal, non-inherited subprocess environment (T-02-05-02: generated
  code must never read `OPENAI_API_KEY`/`DATABASE_URL`/`REDIS_URL` via
  `os.environ`, even if the denylist is somehow bypassed)
- whole-process-group timeout kill (`start_new_session=True` +
  `os.killpg`), not just the direct child PID, with an explicit `SIGKILL`
  fallback and a final `await proc.wait()` reap so no zombie is left behind

`tests` is literal source appended directly after `code` (matching Pattern
3's `script.write_text(code + "\\n\\n" + tests)` exactly) — e.g. a sequence
of `assert` statements. A failed `assert` raises `AssertionError`, which
Python's default excepthook prints to stderr and exits non-zero on its own;
no separate pass/fail protocol is needed.
"""

import asyncio
import ast
import os
import resource
import signal
import tempfile
import time
from pathlib import Path

from algorunner.schemas.execution import ExecutionResult

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


def _limit_resources() -> None:
    # Each limit is applied independently and defensively: macOS/Darwin's
    # kernel does not back every POSIX rlimit the same way Linux does (e.g.
    # RLIMIT_AS reliably raises "ValueError: current limit exceeds maximum
    # limit" on this project's macOS dev hosts even though the value passed
    # is well-formed) — a limit that the host kernel silently doesn't
    # support must not abort subprocess creation entirely and take every
    # OTHER limit down with it. Production containers run Linux, where all
    # three are enforced; this project's local dev/test loop runs on macOS,
    # where best-effort degrades instead of crashing every executor call.
    for limit, value in (
        (resource.RLIMIT_CPU, (5, 5)),
        (resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024)),
        (resource.RLIMIT_NPROC, (0, 0)),  # blocks fork() — no fork bombs
    ):
        try:
            resource.setrlimit(limit, value)
        except (ValueError, OSError):
            pass
    # Deliberately NOT setting the file-size-zero limit — see module
    # docstring and CLAUDE.md "What NOT to Use" (SIGXFSZ footgun on any
    # file write, including stderr).


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

            proc = await asyncio.create_subprocess_exec(
                "python3",
                str(script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmp,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                start_new_session=True,
                preexec_fn=_limit_resources,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_s
                )
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(0.5)
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()  # reap — never leave a zombie
                duration_ms = int((time.monotonic() - started) * 1000)
                return ExecutionResult(
                    passed=False,
                    stdout="",
                    stderr="timed out",
                    exit_code=-1,
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.monotonic() - started) * 1000)
            return ExecutionResult(
                passed=proc.returncode == 0,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode,
                duration_ms=duration_ms,
            )
