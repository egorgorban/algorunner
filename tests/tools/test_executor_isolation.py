"""CR-01 proofs: generated code is dropped to uid 65534 when the worker is
root, runs under `python3 -S` with a PATH-only env, and the denylists are
extended.

The suite runs as a normal user. Tests needing the root code path patch
`process._euid` to return 0 AND replace `asyncio.create_subprocess_exec` with
a spy that raises a sentinel (a real spawn with user=65534 as non-root would
fail) and `os.chown` with a recorder. No test performs a real chown/setuid.
"""

import asyncio
import os
from pathlib import Path

import pytest

import algorunner.tools.go_executor.subprocess_backend as go_backend
import algorunner.tools.process as process_module
import algorunner.tools.python_executor.subprocess_backend as py_backend
from algorunner.tools.go_executor.subprocess_backend import (
    SubprocessGoExecutor,
    _check_go_denylist,
)
from algorunner.tools.process import (
    PrivilegeDropUnavailableError,
    prepare_workdir,
    run_in_process_group,
    spawn_identity_kwargs,
)
from algorunner.tools.python_executor.subprocess_backend import (
    SubprocessPythonExecutor,
    _check_denylist,
)

FLAG = "ALGORUNNER_REQUIRE_PRIVILEGE_DROP"


class _Sentinel(Exception):
    pass


@pytest.fixture(autouse=True)
def _no_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


def _as_root(monkeypatch) -> None:
    monkeypatch.setattr(process_module, "_euid", lambda: 0)


class _Spy:
    def __init__(self, chowns: list) -> None:
        self.calls: list[tuple[tuple, dict]] = []
        self.chowns_at_call: list[int] = []
        self._chowns = chowns

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.chowns_at_call.append(len(self._chowns))
        raise _Sentinel


def _install_spies(monkeypatch) -> tuple[_Spy, list]:
    chowns: list[tuple] = []

    def _chown(path, uid, gid, *, follow_symlinks=True):
        chowns.append((str(path), uid, gid, follow_symlinks))

    monkeypatch.setattr(os, "chown", _chown)
    spy = _Spy(chowns)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy)
    return spy, chowns


# --- identity -------------------------------------------------------------


def test_identity_kwargs_for_root(monkeypatch):
    _as_root(monkeypatch)
    assert spawn_identity_kwargs() == {"user": 65534, "group": 65534, "extra_groups": []}


def test_identity_kwargs_empty_for_non_root(monkeypatch):
    monkeypatch.setattr(process_module, "_euid", lambda: 501)
    assert spawn_identity_kwargs() == {}


def test_fail_closed_when_flag_set_and_non_root(monkeypatch):
    monkeypatch.setattr(process_module, "_euid", lambda: 501)
    monkeypatch.setenv(FLAG, "1")
    with pytest.raises(PrivilegeDropUnavailableError):
        spawn_identity_kwargs()


def test_flag_set_and_root_returns_kwargs(monkeypatch):
    _as_root(monkeypatch)
    monkeypatch.setenv(FLAG, "1")
    assert spawn_identity_kwargs()["user"] == 65534


# --- workdir ownership ----------------------------------------------------


def _make_tree(root: Path) -> None:
    (root / "sub").mkdir()
    (root / "sub" / "f.txt").write_text("x")
    (root / "file.txt").write_text("y")
    (root / "link").symlink_to(root / "file.txt")


def test_prepare_workdir_chowns_every_entry_as_root(monkeypatch, tmp_path):
    _as_root(monkeypatch)
    _spy, chowns = _install_spies(monkeypatch)
    _make_tree(tmp_path)
    prepare_workdir(tmp_path)
    paths = {c[0] for c in chowns}
    assert paths == {
        str(tmp_path),
        str(tmp_path / "sub"),
        str(tmp_path / "sub" / "f.txt"),
        str(tmp_path / "file.txt"),
        str(tmp_path / "link"),
    }
    assert all(c[1:] == (65534, 65534, False) for c in chowns)


def test_prepare_workdir_noop_when_non_root(monkeypatch, tmp_path):
    monkeypatch.setattr(process_module, "_euid", lambda: 501)
    _spy, chowns = _install_spies(monkeypatch)
    _make_tree(tmp_path)
    prepare_workdir(tmp_path)
    assert chowns == []


# --- spawn kwargs ---------------------------------------------------------


async def test_spawn_kwargs_as_root(monkeypatch, tmp_path):
    _as_root(monkeypatch)
    spy, _ = _install_spies(monkeypatch)

    def limit() -> None:
        return None

    with pytest.raises(_Sentinel):
        await run_in_process_group(
            ["true"], cwd=str(tmp_path), env={}, timeout_s=5, limit_fn=limit
        )
    _args, kwargs = spy.calls[0]
    assert kwargs["user"] == 65534
    assert kwargs["group"] == 65534
    assert kwargs["extra_groups"] == []
    assert kwargs["start_new_session"] is True
    assert kwargs["preexec_fn"] is limit


async def test_spawn_kwargs_as_non_root(monkeypatch, tmp_path):
    monkeypatch.setattr(process_module, "_euid", lambda: 501)
    spy, _ = _install_spies(monkeypatch)
    with pytest.raises(_Sentinel):
        await run_in_process_group(["true"], cwd=str(tmp_path), env={}, timeout_s=5)
    _args, kwargs = spy.calls[0]
    assert not {"user", "group", "extra_groups"} & kwargs.keys()


# --- executors as root ----------------------------------------------------


async def test_python_executor_as_root_chowns_before_spawn(monkeypatch):
    _as_root(monkeypatch)
    spy, chowns = _install_spies(monkeypatch)
    with pytest.raises(_Sentinel):
        await SubprocessPythonExecutor().run("x = 1\n", "", timeout_s=5)
    args, kwargs = spy.calls[0]
    assert kwargs["user"] == 65534
    assert list(args[:2]) == ["python3", "-S"]
    assert spy.chowns_at_call[0] >= 2
    names = {Path(c[0]).name for c in chowns}
    assert "solution.py" in names
    assert Path(args[2]).name == "solution.py"
    assert Path(args[2]).parent.name in {Path(c[0]).name for c in chowns}


async def test_python_executor_as_non_root_no_chown_and_passes(monkeypatch):
    monkeypatch.setattr(process_module, "_euid", lambda: 501)
    chowns: list = []
    monkeypatch.setattr(os, "chown", lambda *a, **k: chowns.append(a))
    result = await SubprocessPythonExecutor().run(
        "def double(x):\n    return x * 2\n", "assert double(2) == 4\n", timeout_s=10
    )
    assert result.passed, result.stderr
    assert chowns == []


async def test_go_executor_as_root_chowns_tree_before_build(monkeypatch):
    _as_root(monkeypatch)
    spy, chowns = _install_spies(monkeypatch)
    with pytest.raises(_Sentinel):
        await SubprocessGoExecutor().run("package main\n", "", timeout_s=5)
    args, kwargs = spy.calls[0]
    assert kwargs["user"] == 65534
    assert list(args[:2]) == ["go", "build"]
    names = {Path(c[0]).name for c in chowns}
    assert {"main.go", "go.mod", "gocache", "gomodcache"} <= names
    assert len(names) >= 5  # plus the run dir itself


# --- real execution: -S and env scrub -------------------------------------


async def test_python_child_has_scrubbed_env_and_no_site_packages(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-canary")
    tests = (
        "import os, sys, importlib.util\n"
        "assert 'OPENAI_API_KEY' not in os.environ\n"
        "assert not any('site-packages' in p for p in sys.path), sys.path\n"
        "assert importlib.util.find_spec('psycopg') is None\n"
    )
    code = (
        "import math\nimport heapq\nfrom collections import deque\n\n"
        "def f(x):\n    h = [x]\n    heapq.heapify(h)\n    return math.floor(deque(h)[0])\n"
    )
    result = await SubprocessPythonExecutor().run(code, tests + "assert f(3) == 3\n", timeout_s=10)
    assert result.passed, result.stderr


def test_python_spawn_args_use_dash_s():
    assert Path(py_backend.__file__).read_text().count('"-S"') >= 1


# --- denylists ------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("import urllib.request", "urllib"),
        ("from http import client", "http"),
        ("import asyncio", "asyncio"),
        ("import importlib", "importlib"),
        ("import posix", "posix"),
        ("import ssl", "ssl"),
        ("import socketserver", "socketserver"),
        ('__import__("socket")', "__import__"),
        ("x = y.__import__", "__import__"),
        ("z = __builtins__", "__builtins__"),
    ],
)
def test_python_denylist_extended(code, expected):
    assert _check_denylist(code) == expected


def test_python_denylist_allows_typical_imports():
    code = "\n".join(
        f"import {m}" for m in
        ("collections", "heapq", "bisect", "functools", "itertools", "math", "typing", "re", "string")
    )
    assert _check_denylist(code) is None


@pytest.mark.parametrize("path", ["crypto/tls", "plugin", "C"])
def test_go_denylist_extended(path):
    assert _check_go_denylist(f'package main\n\nimport "{path}"\n') == path
    assert _check_go_denylist(f'package main\n\nimport (\n\t"fmt"\n\t"{path}"\n)\n') == path


def test_go_denylist_allows_typical_imports():
    code = 'package main\n\nimport (\n\t"sort"\n\t"strings"\n\t"math"\n\t"container/heap"\n)\n'
    assert _check_go_denylist(code) is None


async def _no_spawn(monkeypatch) -> list:
    spawned: list = []

    async def _spy(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("must not spawn")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy)
    return spawned


async def test_python_executor_rejects_new_denied_import(monkeypatch):
    spawned = await _no_spawn(monkeypatch)
    result = await SubprocessPythonExecutor().run("import ssl\n", "", timeout_s=5)
    assert result.passed is False
    assert "Disallowed import: ssl" in result.stderr
    assert spawned == []


async def test_go_executor_rejects_new_denied_import(monkeypatch):
    spawned = await _no_spawn(monkeypatch)
    result = await SubprocessGoExecutor().run(
        'package main\n\nimport "crypto/tls"\n', "", timeout_s=5
    )
    assert result.passed is False
    assert "Disallowed import: crypto/tls" in result.stderr
    assert spawned == []


def test_go_backend_uses_prepare_workdir():
    assert "prepare_workdir" in Path(go_backend.__file__).read_text()
