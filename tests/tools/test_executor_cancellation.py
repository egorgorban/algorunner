"""CR-02 proofs: cancelling or timing out an executor call kills the child's
whole process group on every exit path, and the Go binary runs under rlimits.

Every test that may leak a child kills the group in its own ``finally`` so a
failing (RED) run never leaves orphans behind.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

import algorunner.tools.go_executor.subprocess_backend as go_backend
import algorunner.worker.tasks as worker_tasks
from algorunner.schemas.task import Language, TaskStatus, TaskSubmission
from algorunner.storage.tasks import get_task, insert_task
from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor


def group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def wait_for_pidfile(path: Path, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = path.read_text().strip()
            if text:
                return int(text)
        except (FileNotFoundError, ValueError):
            pass
        await asyncio.sleep(0.05)
    raise AssertionError(f"pid file {path} never appeared")


async def wait_until_group_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not group_alive(pid):
            return True
        await asyncio.sleep(0.05)
    return not group_alive(pid)


def _kill_group(pid: int | None) -> None:
    if pid is None:
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _sleeper_tests(pidfile: Path) -> str:
    return (
        "import os, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )


_MINIMAL_GO = 'package main\n\nfunc double(x int) int { return x * 2 }\n'


async def test_python_cancel_kills_process_group(tmp_path):
    pidfile = tmp_path / "pid"
    pid: int | None = None
    task = asyncio.create_task(
        SubprocessPythonExecutor().run("", _sleeper_tests(pidfile), timeout_s=60)
    )
    try:
        pid = await wait_for_pidfile(pidfile, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await wait_until_group_gone(pid, 3)
    finally:
        _kill_group(pid)
        task.cancel()


async def test_go_build_step_cancel_kills_process_group(tmp_path, monkeypatch):
    pidfile = tmp_path / "pid"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_go = fake_bin / "go"
    fake_go.write_text(f"#!/bin/sh\necho $$ > {pidfile}\nexec sleep 60\n")
    fake_go.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ.get('PATH', '')}")

    pid: int | None = None
    task = asyncio.create_task(SubprocessGoExecutor().run(_MINIMAL_GO, "", timeout_s=60))
    try:
        pid = await wait_for_pidfile(pidfile, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await wait_until_group_gone(pid, 3)
    finally:
        _kill_group(pid)
        task.cancel()


async def test_go_run_step_cancel_kills_process_group(tmp_path):
    pidfile = tmp_path / "pid"
    code = (
        "package main\n\n"
        'import (\n\t"os"\n\t"strconv"\n)\n\n'
        "func spin() {\n"
        f"\t_ = os.WriteFile({json.dumps(str(pidfile))}, "
        "[]byte(strconv.Itoa(os.Getpid())), 0o644)\n"
        "\tfor {\n\t}\n}\n"
    )
    pid: int | None = None
    task = asyncio.create_task(SubprocessGoExecutor().run(code, "spin()", timeout_s=60))
    try:
        pid = await wait_for_pidfile(pidfile, 60)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await wait_until_group_gone(pid, 3)
    finally:
        _kill_group(pid)
        task.cancel()


class _State(TypedDict):
    x: int


async def test_global_timeout_through_invoke_with_budget_kills_child(
    pg_pool, tmp_path, monkeypatch
):
    pidfile = tmp_path / "pid"

    async def node(state: _State) -> _State:
        await SubprocessPythonExecutor().run("", _sleeper_tests(pidfile), timeout_s=60)
        return {"x": 1}

    builder = StateGraph(_State)
    builder.add_node("run", node)
    builder.add_edge(START, "run")
    builder.add_edge("run", END)
    graph = builder.compile(checkpointer=InMemorySaver())

    monkeypatch.setattr(worker_tasks.settings, "global_timeout_s", 3)
    task_id = uuid4()
    await insert_task(pg_pool, task_id, TaskSubmission(problem_text="x", language=Language.EN))

    pid: int | None = None
    try:
        result = await worker_tasks._invoke_with_budget(
            graph, {"x": 0}, {"configurable": {"thread_id": str(task_id)}}, str(task_id)
        )
        assert result is None
        record = await get_task(pg_pool, task_id)
        assert record.status == TaskStatus.FAILED
        assert record.error.code == "GLOBAL_TIMEOUT"
        pid = await wait_for_pidfile(pidfile, 1)
        assert await wait_until_group_gone(pid, 3)
    finally:
        if pidfile.exists():
            try:
                pid = int(pidfile.read_text().strip())
            except ValueError:
                pass
        _kill_group(pid)


async def test_timeout_path_kills_group_and_returns_none(tmp_path):
    from algorunner.tools.process import run_in_process_group

    pidfile = tmp_path / "pid"
    script = (
        "import os, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    pid: int | None = None
    try:
        result = await run_in_process_group(
            [sys.executable, "-c", script],
            cwd=str(tmp_path),
            env={"PATH": os.environ.get("PATH", "")},
            timeout_s=1.5,
        )
        assert result is None
        pid = await wait_for_pidfile(pidfile, 1)
        assert await wait_until_group_gone(pid, 3)
    finally:
        _kill_group(pid)


_PRINT_LIMITS = (
    "import resource\n"
    "print(resource.getrlimit(resource.RLIMIT_CPU), resource.getrlimit(resource.RLIMIT_NOFILE))\n"
)


def _limits_of(limit_fn) -> str:
    out = subprocess.run(
        [sys.executable, "-c", _PRINT_LIMITS],
        preexec_fn=limit_fn,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_rlimit_profile_applied():
    from algorunner.tools.process import make_limit_fn

    fn = make_limit_fn(cpu_s=7, address_space_bytes=None, open_files=256, max_processes=None)
    assert _limits_of(fn) == "(7, 7) (256, 256)"

    go_fn = go_backend._go_run_limits(30.0)
    assert _limits_of(go_fn) == "(60, 60) (256, 256)"


async def test_go_executor_passes_limits_only_to_run_step(monkeypatch):
    calls: list[dict] = []

    async def recorder(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return b"", b"", 0

    monkeypatch.setattr(go_backend, "run_in_process_group", recorder)
    result = await SubprocessGoExecutor().run(_MINIMAL_GO, "", timeout_s=5)

    assert result.passed
    assert len(calls) == 2
    assert calls[0]["args"][:2] == ["go", "build"]
    assert calls[0].get("limit_fn") is None
    assert callable(calls[1]["limit_fn"])
