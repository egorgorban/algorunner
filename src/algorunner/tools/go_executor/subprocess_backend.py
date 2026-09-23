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
SAME process-group kill/reap helper (`tools.process.run_in_process_group`,
which also kills on cancellation) — a hung
`go build` needs the same kill treatment as a hung generated binary, per
this plan's `<action>`.

The import denylist is a best-effort text scan against accidental misuse,
NOT a security boundary (bypassable via dot-imports, `os.StartProcess`). The
real boundary is uid separation, documented with the accepted residual risks
in `algorunner.tools.process`.
"""

import math
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from algorunner.schemas.execution import ExecutionResult
from algorunner.tools.process import make_limit_fn, prepare_workdir, run_in_process_group

_DENYLISTED_GO_IMPORTS = ("net", "os/exec", "syscall", "unsafe", "crypto/tls", "plugin", "C")

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


def _go_run_limits(timeout_s: float) -> Callable[[], None]:
    """rlimits for the compiled Go binary (never for `go build`).

    CPU is only a backstop far above the wall-clock kill: multi-threaded Go
    GC can burn more CPU-seconds than wall-seconds, so a tight cap could kill
    a correct solution. Address space is deliberately generous because the Go
    runtime reserves large virtual ranges up front (do not lower it toward the
    Python 512 MiB). NPROC is omitted because the Go runtime creates OS
    threads and NPROC=0 would crash it.
    """
    return make_limit_fn(
        cpu_s=max(2 * math.ceil(timeout_s), 2),
        address_space_bytes=4 * 1024 * 1024 * 1024,
        open_files=256,
        max_processes=None,
    )


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

            # Tree is fully populated: hand it to the unprivileged uid once,
            # before any child (including `go build`) starts.
            prepare_workdir(tmp)

            binary = tmp / "solution"
            build_env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GOCACHE": str(gocache),
                "GOMODCACHE": str(gomodcache),
                "HOME": str(tmp),
            }
            build_out = await run_in_process_group(
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

            run_out = await run_in_process_group(
                [str(binary)],
                cwd=str(tmp),
                env={},
                timeout_s=timeout_s,
                limit_fn=_go_run_limits(timeout_s),
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
