"""Single owner of child-process lifecycle and resource limits for both code
executors (Python and Go).

Everything that spawns, times out, kills or reaps generated-code children
lives here, so the guarantees below hold identically for the Python run, the
Go build step and the Go run step:

- the child runs in its own session/process group (``start_new_session``),
- on ANY exit path (normal, timeout, ``CancelledError`` from the global
  timeout or a worker shutdown, any other exception) the whole group is
  hard-killed and the leader is reaped (CR-02, INFRA-04, D-08).
"""

import asyncio
import contextlib
import os
import resource
import signal
from collections.abc import Callable

_REAP_TIMEOUT_S = 5.0


def make_limit_fn(
    *,
    cpu_s: int,
    address_space_bytes: int | None,
    open_files: int,
    max_processes: int | None,
) -> Callable[[], None]:
    """Build a zero-argument function (for ``preexec_fn``) applying rlimits.

    Each limit is applied independently and defensively: some kernels do not
    back every POSIX rlimit the way Linux does (RLIMIT_AS raises ValueError on
    this project's macOS dev hosts even for a well-formed value), and a limit
    the host cannot honor must not abort the spawn or skip the other limits.

    A file-size limit is deliberately never set: a zero file-size cap makes
    the kernel kill the process with SIGXFSZ on any regular-file write,
    including inherited stderr, producing confusing false "crashes"
    (CLAUDE.md "What NOT to Use").
    """
    limits: list[tuple[int, int]] = [
        (resource.RLIMIT_CPU, cpu_s),
        (resource.RLIMIT_NOFILE, open_files),
    ]
    if address_space_bytes is not None:
        limits.append((resource.RLIMIT_AS, address_space_bytes))
    if max_processes is not None:
        limits.append((resource.RLIMIT_NPROC, max_processes))

    def _apply() -> None:
        for limit, value in limits:
            try:
                resource.setrlimit(limit, (value, value))
            except (ValueError, OSError):
                pass

    return _apply


def kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """Hard-kill the child's whole process group if the leader is still
    unreaped.

    The pgid equals the pid because callers always spawn with
    ``start_new_session=True``. The ``returncode is None`` guard avoids
    signalling a recycled pid after asyncio has already reaped the leader.
    """
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)


async def run_in_process_group(
    args: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    timeout_s: float,
    limit_fn: Callable[[], None] | None = None,
) -> tuple[bytes, bytes, int] | None:
    """Run ``args`` in its own process group.

    Returns ``(stdout, stderr, returncode)``, or ``None`` on timeout (the
    caller builds the timeout result). The ``finally`` kill-and-reap covers
    timeout, cancellation and every other exit path (CR-02); it never
    swallows ``CancelledError``. Single hard-kill step, no graceful phase:
    generated code has no cleanup duty and a sleep in the cancel path would
    itself be a cancellation point.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,
        preexec_fn=limit_fn,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        return None
    finally:
        kill_process_group(proc)
        # Bounded reap: a child stuck in uninterruptible sleep must never
        # hang the worker.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)
    assert proc.returncode is not None
    return stdout, stderr, proc.returncode
