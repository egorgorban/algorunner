"""Single owner of child-process lifecycle, resource limits and privilege
separation for both code executors (Python and Go).

Everything that spawns, times out, kills or reaps generated-code children
lives here, so the guarantees below hold identically for the Python run, the
Go build step and the Go run step:

- the child runs in its own session/process group (``start_new_session``),
- on ANY exit path (normal, timeout, ``CancelledError`` from the global
  timeout or a worker shutdown, any other exception) the whole group is
  hard-killed and the leader is reaped (CR-02, INFRA-04, D-08).

TRUST MODEL (read before relying on any control here)

1. The security boundary is uid separation. The worker stays root (changing
   the child's uid needs root; a non-root worker would need CAP_SETUID) and
   every child runs as uid/gid 65534 with no supplementary groups; the drop
   is performed in ``preexec_fn`` (setgroups, setgid, setuid, then rlimits).
   It therefore cannot open ``/proc/1/environ`` or ``/proc/<worker pid>/environ``
   where ``OPENAI_API_KEY``, ``DATABASE_URL`` and ``REDIS_URL`` live. This
   applies only when the worker's euid is 0; otherwise (developer hosts)
   nothing changes.
2. The environment allowlist (PATH only for Python) merely stops the trivial
   ``os.environ`` read. It is not a secrecy control.
3. The import denylists and ``python3 -S`` are best-effort filters against
   accidental misuse. They are not a secrecy or network control and are
   bypassable (``getattr`` / ``__builtins__`` tricks in Python,
   ``os.StartProcess`` and dot-imports in Go).
4. Accepted v1 RESIDUAL RISKS: outbound network egress and lateral access to
   postgres/redis with default credentials remain open. A kernel-enforced
   control needs NET_ADMIN or CAP_SYS_ADMIN or a separate sandbox, which is
   SEC-02/SEC-03 (v2); a uid-owner iptables rule for uid 65534 is the
   recommended first step. All concurrent runs share uid 65534, so one run can
   signal another. Go has no NPROC limit (the runtime needs OS threads).
5. ``ALGORUNNER_REQUIRE_PRIVILEGE_DROP`` (set in the worker image) makes a
   non-root worker fail loudly with ``PrivilegeDropUnavailableError`` instead
   of silently running generated code under the worker's own uid, which would
   re-open the /proc environ leak (D-00f: fail loudly, never downgrade).
"""

import asyncio
import contextlib
import os
import resource
import signal
from collections.abc import Callable
from pathlib import Path

_REAP_TIMEOUT_S = 5.0

UNPRIVILEGED_UID = 65534
UNPRIVILEGED_GID = 65534
REQUIRE_PRIVILEGE_DROP_ENV = "ALGORUNNER_REQUIRE_PRIVILEGE_DROP"


class PrivilegeDropUnavailableError(RuntimeError):
    """Raised when the privilege drop is required but the worker is not root."""


def _euid() -> int:
    # Patch point for tests; every privilege decision goes through it.
    return os.geteuid()


def make_preexec_fn(limit_fn: Callable[[], None] | None) -> Callable[[], None] | None:
    """Build the ``preexec_fn`` for a child spawn.

    The decision is made here, in the parent. As root the result drops to
    uid/gid 65534 (setgroups, setgid, setuid) and then applies ``limit_fn``.
    Non-root returns ``limit_fn`` unchanged. If the drop is required (image
    flag) but the worker is not root, raise instead of degrading (D-00f).
    """
    if _euid() == 0:

        def _drop_then_limit() -> None:
            """Runs in the forked child (uvloop and CPython both call
            ``preexec_fn`` there): only ``os.*`` syscalls and the rlimit
            function; no logging, no ``_euid()``/environment lookups.

            Exceptions are deliberately never caught: any OSError aborts the
            spawn (the child never execs and the parent raises
            ``subprocess.SubprocessError``), which is the fail-closed
            behavior. OSError carries args, so uvloop's error-pipe report
            works. Order matters: groups and gid can only change while still
            root, and setuid drops real/effective/saved ids irrevocably, so a
            failure at any step can never leave a child that execs as root.
            """
            os.setgroups([])
            os.setgid(UNPRIVILEGED_GID)
            os.setuid(UNPRIVILEGED_UID)
            if limit_fn is not None:
                limit_fn()

        return _drop_then_limit
    if os.environ.get(REQUIRE_PRIVILEGE_DROP_ENV, "").strip().lower() in {"1", "true", "yes"}:
        raise PrivilegeDropUnavailableError(
            "Privilege drop is required but the worker is not root: generated "
            "code would run under the worker's own uid and could read its "
            "/proc environ (API key, database and redis URLs)."
        )
    return limit_fn


def prepare_workdir(path: Path) -> None:
    """Chown `path` and everything beneath it to the unprivileged uid.

    No-op unless the worker is root. Call exactly once, after the tree is
    fully populated and before any child starts (no child-controlled symlink
    race exists at chown time).
    """
    if _euid() != 0:
        return
    os.chown(path, UNPRIVILEGED_UID, UNPRIVILEGED_GID, follow_symlinks=False)
    for dirpath, dirnames, filenames in os.walk(path):
        for name in (*dirnames, *filenames):
            os.chown(
                os.path.join(dirpath, name),
                UNPRIVILEGED_UID,
                UNPRIVILEGED_GID,
                follow_symlinks=False,
            )


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
    # The privilege drop is done inside preexec_fn, NOT via user/group/
    # extra_groups spawn kwargs: the worker and API run on uvloop (taskiq's
    # worker selects it whenever importable, uvicorn `auto` does the same) and
    # uvloop.Loop.subprocess_exec rejects identity keywords with ValueError.
    # Ordering inside the composed function is load-bearing: rlimits come after
    # setuid because on Linux set_user() flags PF_NPROC_EXCEEDED if RLIMIT_NPROC
    # is already exceeded, which makes the following execve fail with EAGAIN
    # (so RLIMIT_NPROC=0 must follow the uid change). Do not reintroduce spawn
    # kwargs for identity and do not move the limits before the drop.
    preexec = make_preexec_fn(limit_fn)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
        start_new_session=True,
        preexec_fn=preexec,
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
