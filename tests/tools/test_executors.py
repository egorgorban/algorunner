"""Executor tool tests (EXEC-01/02/03).

Python tests (Task 1) cover: happy path, process-group timeout kill, and the
static import denylist. Go tests (Task 2, added below the Python section)
cover the same three scenarios translated to Go's compile+run model.

`tests` strings passed to `.run(code, tests, ...)` are literal source code
appended after `code` (Python: `assert` statements; Go: statements executed
inside a generated `func main`) — matching RESEARCH.md Pattern 3's verified
example (`script.write_text(code + "\\n\\n" + tests)`), not a separate
data-interchange format. Test-writer-controlled here; `_render_test_harness`
in `graph/build.py` (Task 3) is responsible for producing this shape from
`Solution.tests` in production.
"""

import asyncio
import time

from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor


async def test_python_executor_runs_correct_solution():
    code = "def double(x):\n    return x * 2\n"
    tests = "assert double(2) == 4\nassert double(3) == 6\n"

    result = await SubprocessPythonExecutor().run(code, tests, timeout_s=5.0)

    assert result.passed is True
    assert result.exit_code == 0
    assert result.stderr == ""


async def test_python_executor_reports_failure_on_assertion_error():
    code = "def double(x):\n    return x * 2\n"
    tests = "assert double(2) == 5\n"

    result = await SubprocessPythonExecutor().run(code, tests, timeout_s=5.0)

    assert result.passed is False
    assert result.exit_code != 0
    assert "AssertionError" in result.stderr


async def test_python_executor_kills_infinite_loop_via_process_group():
    code = "while True:\n    pass\n"
    tests = ""

    start = time.monotonic()
    result = await SubprocessPythonExecutor().run(code, tests, timeout_s=1.0)
    elapsed = time.monotonic() - start

    # Returns promptly (not hanging the worker/test suite) and reports a
    # clean, non-hanging failure. The executor's own `await proc.wait()`
    # completing without raising (no exception propagated to this test) is
    # the evidence that no zombie/orphan process was left behind — no
    # `psutil` dependency exists in this project to assert on the OS
    # process table directly.
    assert elapsed < 5.0
    assert result.passed is False
    assert result.exit_code == -1


async def test_python_executor_rejects_denylisted_import_without_spawning_subprocess(
    monkeypatch,
):
    code = "import os\n\n\ndef f():\n    return os.getcwd()\n"
    tests = ""

    spawned = False
    original_create_subprocess_exec = asyncio.create_subprocess_exec

    async def _spy_create_subprocess_exec(*args, **kwargs):
        nonlocal spawned
        spawned = True
        return await original_create_subprocess_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy_create_subprocess_exec)

    result = await SubprocessPythonExecutor().run(code, tests, timeout_s=5.0)

    assert result.passed is False
    assert "Disallowed import: os" in result.stderr
    assert result.exit_code == -1
    assert spawned is False
