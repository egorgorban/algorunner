"""Subprocess-based `CodeExecutor` for generated Go code (EXEC-02).

Compiles the generated code into the pre-seeded `go-template` scaffold
(RESEARCH.md Pitfall 3 — a checked-in template `go.mod` avoids ambient
`GOPATH`/module-resolution surprises) and executes the resulting binary
directly (`go build` then run the binary — never `go run`, so exactly one
PID tree needs to die on a timeout, per RESEARCH.md Pattern 3/Pitfall 2).

`code` is a complete Go file body (`package main` + whatever imports/funcs
the solution needs, no `func main`); `tests` is Go source executed inside a
generated `func main() { ... }` — the same code+tests convention as
`python_executor/subprocess_backend.py`, translated to Go's compile+run
model (a caller wanting `os.Exit(1)` inside `tests` must import "os" in
`code` itself — this module does not inject extra imports beyond what
`code` already declares).

Both the `go build` step and the compiled binary's run step go through the
SAME process-group timeout-kill/reap helper (`_run_with_timeout`) — a hung
`go build` needs the same kill treatment as a hung generated binary, per
this plan's `<action>`.
"""

import asyncio
import os
import re
import shutil
import signal
import tempfile
import time
from pathlib import Path

from algorunner.schemas.execution import ExecutionResult

_DENYLISTED_GO_IMPORTS = ("net", "os/exec", "syscall", "unsafe")

# Repo root: subprocess_backend.py lives at
# <repo_root>/src/algorunner/tools/go_executor/subprocess_backend.py in both
# the local dev tree and the worker Docker image (`COPY src ./src`,
# `COPY go-template ./go-template` both land relative to the same WORKDIR).
_GO_TEMPLATE_DIR = Path(__file__).resolve().parents[4] / "go-template"

_IMPORT_BLOCK_RE = re.compile(r"import\s*\(([^)]*)\)", re.DOTALL)
_IMPORT_SINGLE_RE = re.compile(r'import\s+(?:\w+\s+)?"([^"]+)"')
_QUOTED_PATH_RE = re.compile(r'"([^"]+)"')


def _check_go_denylist(code: str) -> str | None:
    """Returns the first denylisted import path (or its parent package)
    found in `code`'s `import (...)` block or single-line `import "..."`
    statements, or `None` if clean. A path matches if it equals a
    denylisted entry or is a subpackage of one (e.g. `net/http` matches
    `net`)."""
    import_paths: list[str] = []
    for block in _IMPORT_BLOCK_RE.findall(code):
        import_paths.extend(_QUOTED_PATH_RE.findall(block))
    import_paths.extend(_IMPORT_SINGLE_RE.findall(code))

    for path in import_paths:
        for denied in _DENYLISTED_GO_IMPORTS:
            if path == denied or path.startswith(denied + "/"):
                return denied
    return None


async def _run_with_timeout(
    args: list[str], *, cwd: str, env: dict[str, str], timeout_s: float
) -> tuple[bytes, bytes, int] | None:
    """Runs `args` under its own process group, killing the whole group on
    timeout. Returns `(stdout, stderr, returncode)`, or `None` on timeout —
    the caller builds the timeout `ExecutionResult`. Shared by both the
    `go build` step and the compiled binary's run step."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
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
        return None
    return stdout, stderr, proc.returncode


def _timeout_result(started: float) -> ExecutionResult:
    return ExecutionResult(
        passed=False,
        stdout="",
        stderr="timed out",
        exit_code=-1,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


class SubprocessGoExecutor:
    """`CodeExecutor` implementation compiling and running generated Go via
    `go build` + direct binary execution (never `go run`)."""

    async def run(
        self, code: str, tests: str, *, timeout_s: float = 10.0
    ) -> ExecutionResult:
        disallowed = _check_go_denylist(code)
        if disallowed is not None:
            return ExecutionResult(
                passed=False,
                stdout="",
                stderr=f"Disallowed import: {disallowed}",
                exit_code=-1,
                duration_ms=0,
            )

        started = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            shutil.copytree(_GO_TEMPLATE_DIR, tmp, dirs_exist_ok=True)

            main_go = tmp / "main.go"
            main_go.write_text(code + "\n\nfunc main() {\n" + tests + "\n}\n")

            gocache = tmp / "gocache"
            gomodcache = tmp / "gomodcache"
            gocache.mkdir(exist_ok=True)
            gomodcache.mkdir(exist_ok=True)

            binary = tmp / "solution"
            build_env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GOCACHE": str(gocache),
                "GOMODCACHE": str(gomodcache),
                "HOME": str(tmp),
            }
            build_out = await _run_with_timeout(
                ["go", "build", "-o", str(binary), str(main_go)],
                cwd=str(tmp),
                env=build_env,
                timeout_s=timeout_s,
            )
            if build_out is None:
                return _timeout_result(started)
            build_stdout, build_stderr, build_rc = build_out
            if build_rc != 0:
                return ExecutionResult(
                    passed=False,
                    stdout=build_stdout.decode(errors="replace"),
                    stderr=build_stderr.decode(errors="replace"),
                    exit_code=build_rc,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )

            run_out = await _run_with_timeout(
                [str(binary)], cwd=str(tmp), env={}, timeout_s=timeout_s
            )
            if run_out is None:
                return _timeout_result(started)
            run_stdout, run_stderr, run_rc = run_out
            return ExecutionResult(
                passed=run_rc == 0,
                stdout=run_stdout.decode(errors="replace"),
                stderr=run_stderr.decode(errors="replace"),
                exit_code=run_rc,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
