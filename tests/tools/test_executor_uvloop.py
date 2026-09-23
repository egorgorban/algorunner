"""Regression suite: the executors must spawn correctly on uvloop.

Root cause of the production failure ("unexpected kwargs: user, group,
extra_groups"): the taskiq worker and uvicorn run on uvloop, and
``uvloop.Loop.subprocess_exec`` rejects the ``user``/``group``/``extra_groups``
keywords that stdlib asyncio accepts. The privilege drop therefore lives inside
``preexec_fn``. Host tests ran only on the stdlib loop as non-root, so the
mistake was invisible.

Harness decision: the suite uses pytest-asyncio with session-scoped default
loops and a session ``pg_pool`` bound to that loop, so the loop policy is NOT
changed suite-wide. Every test here is a plain SYNC function that creates its
own loop with ``asyncio.Runner(loop_factory=...)``. uvloop is imported plainly:
a missing uvloop must fail loudly, never skip the regression.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
import uvloop

import algorunner.tools.process as process_module
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.process import run_in_process_group
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor
from tests.tools.test_executor_cancellation import (
    _kill_group,
    _sleeper_tests,
    wait_for_pidfile,
    wait_until_group_gone,
)

FLAG = "ALGORUNNER_REQUIRE_PRIVILEGE_DROP"

LOOPS = [
    pytest.param(asyncio.new_event_loop, id="asyncio"),
    pytest.param(uvloop.new_event_loop, id="uvloop"),
]


@pytest.fixture(autouse=True)
def _no_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


def _euid_as(monkeypatch, value: int) -> None:
    monkeypatch.setattr(process_module, "_euid", lambda: value)


def run_on(loop_factory: Callable[[], Any], main: Callable[[], Awaitable[Any]]) -> Any:
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(main())


def _install_recorders(
    monkeypatch, log: Path, *, fail_setuid: bool = False
) -> Callable[[], None]:
    """Replace the drop syscalls with file-logging recorders.

    They run only in the forked child; the parent never calls them. Returns a
    recorder standing in for the rlimit function.
    """

    def _append(line: str) -> None:
        with open(log, "a") as fh:
            fh.write(line + "\n")

    def _setgroups(groups) -> None:
        _append(f"setgroups {list(groups)}")

    def _setgid(gid: int) -> None:
        _append(f"setgid {gid}")

    def _setuid(uid: int) -> None:
        if fail_setuid:
            raise PermissionError(1, "Operation not permitted")
        _append(f"setuid {uid}")

    def _limit() -> None:
        _append("limit")

    monkeypatch.setattr(os, "setgroups", _setgroups)
    monkeypatch.setattr(os, "setgid", _setgid)
    monkeypatch.setattr(os, "setuid", _setuid)
    return _limit


def test_helper_really_runs_on_uvloop():
    async def main() -> bool:
        return isinstance(asyncio.get_running_loop(), uvloop.Loop)

    assert run_on(uvloop.new_event_loop, main) is True


@pytest.mark.parametrize("loop_factory", LOOPS)
def test_root_spawn_never_passes_identity_kwargs(monkeypatch, tmp_path, loop_factory):
    _euid_as(monkeypatch, 0)
    log = tmp_path / "drop.log"
    limit = _install_recorders(monkeypatch, log)

    real_spawn = asyncio.create_subprocess_exec
    seen: list[dict] = []

    async def wrapper(*args, **kwargs):
        seen.append(kwargs)
        return await real_spawn(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", wrapper)

    async def main():
        return await run_in_process_group(
            [sys.executable, "-c", "print('spawned')"],
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", "")},
            timeout_s=20,
            limit_fn=limit,
        )

    result = run_on(loop_factory, main)
    assert result == (b"spawned\n", b"", 0)
    assert log.read_text().splitlines() == [
        "setgroups []",
        "setgid 65534",
        "setuid 65534",
        "limit",
    ]
    assert len(seen) == 1
    assert not {"user", "group", "extra_groups"} & seen[0].keys()
    assert callable(seen[0]["preexec_fn"])


@pytest.mark.parametrize("loop_factory", LOOPS)
def test_failed_privilege_drop_aborts_spawn(monkeypatch, tmp_path, loop_factory):
    _euid_as(monkeypatch, 0)
    log = tmp_path / "drop.log"
    limit = _install_recorders(monkeypatch, log, fail_setuid=True)
    marker = tmp_path / "ran"
    code = f"open({str(marker)!r}, 'w').write('x')"

    async def main():
        await run_in_process_group(
            [sys.executable, "-c", code],
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", "")},
            timeout_s=20,
            limit_fn=limit,
        )

    with pytest.raises(subprocess.SubprocessError):
        run_on(loop_factory, main)
    assert not marker.exists()
    assert "limit" not in log.read_text().splitlines()


def test_python_executor_happy_path_on_uvloop(monkeypatch):
    _euid_as(monkeypatch, 501)

    async def main():
        return await SubprocessPythonExecutor().run(
            "def double(x):\n    return x * 2\n", "assert double(2) == 4\n", timeout_s=20
        )

    result = run_on(uvloop.new_event_loop, main)
    assert result.passed, result.stderr


def test_go_executor_happy_path_on_uvloop(monkeypatch):
    _euid_as(monkeypatch, 501)
    code = "package main\n\nfunc double(x int) int { return x * 2 }\n"
    tests = 'if double(2) != 4 {\n\tpanic("bad")\n}\n'

    async def main():
        return await SubprocessGoExecutor().run(code, tests, timeout_s=120)

    result = run_on(uvloop.new_event_loop, main)
    assert result.passed, result.stderr


def test_python_cancel_kills_process_group_on_uvloop(monkeypatch, tmp_path):
    _euid_as(monkeypatch, 501)
    pidfile = tmp_path / "pid"
    pids: list[int] = []

    async def main() -> None:
        task = asyncio.create_task(
            SubprocessPythonExecutor().run("", _sleeper_tests(pidfile), timeout_s=60)
        )
        try:
            pid = await wait_for_pidfile(pidfile, 10)
            pids.append(pid)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await wait_until_group_gone(pid, 3)
        finally:
            task.cancel()

    try:
        run_on(uvloop.new_event_loop, main)
    finally:
        for pid in pids:
            _kill_group(pid)


def test_go_run_step_cancel_kills_process_group_on_uvloop(monkeypatch, tmp_path):
    import json

    _euid_as(monkeypatch, 501)
    pidfile = tmp_path / "pid"
    code = (
        "package main\n\n"
        'import (\n\t"os"\n\t"strconv"\n)\n\n'
        "func spin() {\n"
        f"\t_ = os.WriteFile({json.dumps(str(pidfile))}, "
        "[]byte(strconv.Itoa(os.Getpid())), 0o644)\n"
        "\tfor {\n\t}\n}\n"
    )
    pids: list[int] = []

    async def main() -> None:
        task = asyncio.create_task(SubprocessGoExecutor().run(code, "spin()", timeout_s=60))
        try:
            pid = await wait_for_pidfile(pidfile, 60)
            pids.append(pid)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await wait_until_group_gone(pid, 3)
        finally:
            task.cancel()

    try:
        run_on(uvloop.new_event_loop, main)
    finally:
        for pid in pids:
            _kill_group(pid)


def test_timeout_kills_group_on_uvloop(monkeypatch, tmp_path):
    _euid_as(monkeypatch, 501)
    pidfile = tmp_path / "pid"
    pids: list[int] = []

    async def main() -> None:
        result = await run_in_process_group(
            [sys.executable, "-c", _sleeper_tests(pidfile)],
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", "")},
            timeout_s=1.5,
        )
        assert result is None
        pid = await wait_for_pidfile(pidfile, 1)
        pids.append(pid)
        assert await wait_until_group_gone(pid, 3)

    try:
        run_on(uvloop.new_event_loop, main)
    finally:
        for pid in pids:
            _kill_group(pid)
