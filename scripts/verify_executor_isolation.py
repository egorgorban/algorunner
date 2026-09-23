"""Container-level acceptance probe for the executor uid drop (CR-01) and the
cancellation kill (CR-02).

Run inside the worker image, piped into the same interpreter the worker uses:

    cat scripts/verify_executor_isolation.py | docker run --rm -i \
        -e OPENAI_API_KEY=sk-canary-not-real algorunner-worker:cr01 uv run python -

Prints one `PASS name` / `FAIL name: reason` line per check and never prints
environment content or secrets (booleans and uid/limit numbers only). Exits 2
if not root (inert on developer hosts), 1 on any failure, 0 on success.
"""

import asyncio
import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path

from algorunner.tools.go_executor.subprocess_backend import SubprocessGoExecutor
from algorunner.tools.python_executor.subprocess_backend import SubprocessPythonExecutor

FAILURES: list[str] = []


def check(name: str, ok: bool, reason: str = "") -> None:
    if ok:
        print(f"PASS {name}")
    else:
        FAILURES.append(name)
        print(f"FAIL {name}: {reason}")


def _lines(stdout: str) -> dict[str, str]:
    """Parse `KEY=value` lines printed by probe children."""
    out: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


# Child-side source (passed through the executor's `tests` argument, which is
# not denylist-scanned). Prints numbers/booleans only.
_PY_PROBE = r"""
import os


def _status(prefix):
    for line in open("/proc/self/status"):
        if line.startswith(prefix):
            return line.split(":", 1)[1].split()
    return None


def _limit(prefix):
    for line in open("/proc/self/limits"):
        if line.startswith(prefix):
            parts = line[len(prefix):].split()
            return parts[0] + "/" + parts[1]
    return "missing"


def _read(path):
    try:
        open(path, "rb").read()
        return "LEAK"
    except PermissionError:
        return "DENIED"
    except OSError as exc:
        return "ERR:" + type(exc).__name__


print("UID=" + ",".join(_status("Uid:") or []))
print("GID=" + ",".join(_status("Gid:") or []))
print("GROUPS=" + ",".join(_status("Groups:") or []))
print("ENV1=" + _read("/proc/1/environ"))
print("ENVPARENT=" + _read("/proc/%d/environ" % os.getppid()))
print("NPROC=" + _limit("Max processes"))
print("AS=" + _limit("Max address space"))
print("NOFILE=" + _limit("Max open files"))
print("CPU=" + _limit("Max cpu time"))
try:
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    print("FORK=ALLOWED")
except OSError:
    print("FORK=BLOCKED")
import importlib.util
print("PSYCOPG=" + str(importlib.util.find_spec("psycopg") is not None))
"""

_GO_CODE = (
    "package main\n\n"
    'import (\n\t"fmt"\n\t"os"\n\t"strings"\n)\n\n'
    "func double(x int) int {\n\treturn x * 2\n}\n\n"
    "func field(path, prefix string) string {\n"
    "\tdata, err := os.ReadFile(path)\n"
    "\tif err != nil {\n\t\treturn \"unreadable\"\n\t}\n"
    "\tfor _, line := range strings.Split(string(data), \"\\n\") {\n"
    "\t\tif strings.HasPrefix(line, prefix) {\n"
    "\t\t\treturn strings.Join(strings.Fields(strings.TrimPrefix(line, prefix)), \",\")\n"
    "\t\t}\n\t}\n\treturn \"missing\"\n}\n"
)
_GO_TESTS = """
if double(2) != 4 {
	os.Exit(1)
}
fmt.Println("UID=" + field("/proc/self/status", "Uid:"))
fmt.Println("NPROC=" + field("/proc/self/limits", "Max processes"))
fmt.Println("NOFILE=" + field("/proc/self/limits", "Max open files"))
if _, err := os.ReadFile("/proc/1/environ"); err != nil {
	fmt.Println("ENV1=DENIED")
} else {
	fmt.Println("ENV1=LEAK")
}
"""


def group_alive(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def main() -> int:
    if os.geteuid() != 0:
        print("verify_executor_isolation must run as root inside the worker image")
        return 2

    # 1. Guard env flag.
    check(
        "guard-env",
        os.environ.get("ALGORUNNER_REQUIRE_PRIVILEGE_DROP") == "1",
        "ALGORUNNER_REQUIRE_PRIVILEGE_DROP is not 1",
    )

    # 2. Positive control: root can read PID 1's environ and the canary is there.
    try:
        has_key = b"OPENAI_API_KEY=" in Path("/proc/1/environ").read_bytes()
    except OSError as exc:
        has_key = False
        print(f"note: positive control read failed: {type(exc).__name__}")
    check("positive-control-root-reads-environ", has_key, "root could not see the key in /proc/1/environ")

    py = SubprocessPythonExecutor()
    res = await py.run("", _PY_PROBE, timeout_s=20)
    info = _lines(res.stdout)
    if not res.passed:
        print(f"note: python probe failed with exit code {res.exit_code}")

    # 3. Identity.
    ids = (info.get("UID", "") + "," + info.get("GID", "")).split(",")
    check(
        "python-child-identity",
        res.passed and ids == ["65534"] * 8 and info.get("GROUPS", "x") == "",
        f"uid/gid/groups = {info.get('UID')} {info.get('GID')} [{info.get('GROUPS')}]",
    )

    # 4. Secrets unreadable.
    check(
        "python-child-cannot-read-environ",
        info.get("ENV1") == "DENIED" and info.get("ENVPARENT") == "DENIED",
        f"/proc/1/environ={info.get('ENV1')} parent={info.get('ENVPARENT')}",
    )

    # 5. Limits effective + fork blocked.
    check(
        "python-limits-effective",
        info.get("NPROC") == "0/0"
        and info.get("AS") == "536870912/536870912"
        and info.get("NOFILE") == "256/256"
        and info.get("CPU") == "5/5"
        and info.get("FORK") == "BLOCKED",
        f"NPROC={info.get('NPROC')} AS={info.get('AS')} NOFILE={info.get('NOFILE')} "
        f"CPU={info.get('CPU')} FORK={info.get('FORK')}",
    )

    # 6. -S effective and production-faithful interpreter.
    which = shutil.which("python3") or ""
    check(
        "python-dash-S-effective",
        which.startswith("/app/.venv/bin") and info.get("PSYCOPG") == "False",
        f"python3 resolves to {which!r}; psycopg importable={info.get('PSYCOPG')}",
    )

    # 7. Python happy path.
    ok = await py.run(
        "def double(x):\n    return x * 2\n", "assert double(2) == 4\n", timeout_s=20
    )
    check("python-happy-path", ok.passed, ok.stderr[-200:])

    # 8. Go happy path + identity + limits (real go build as uid 65534).
    go = await SubprocessGoExecutor().run(_GO_CODE, _GO_TESTS, timeout_s=120)
    ginfo = _lines(go.stdout)
    check(
        "go-happy-path-and-identity",
        go.passed
        and ginfo.get("UID") == "65534,65534,65534,65534"
        and ginfo.get("ENV1") == "DENIED",
        f"passed={go.passed} uid={ginfo.get('UID')} env1={ginfo.get('ENV1')} "
        f"stderr={go.stderr[-300:]!r}",
    )
    check(
        "go-limits",
        ginfo.get("NPROC") is not None
        and not ginfo["NPROC"].startswith("0,0")
        and ginfo.get("NOFILE", "").startswith("256,256"),
        f"NPROC={ginfo.get('NPROC')} NOFILE={ginfo.get('NOFILE')}",
    )

    # 9. Cancellation across uids: root worker kills a 65534-owned group.
    work = tempfile.mkdtemp()
    os.chmod(work, 0o777)
    pidfile = Path(work) / "pid"
    sleeper = (
        "import os, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )
    task = asyncio.create_task(py.run("", sleeper, timeout_s=60))
    pid: int | None = None
    gone = False
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and pid is None:
            try:
                pid = int(pidfile.read_text().strip())
            except (FileNotFoundError, ValueError):
                await asyncio.sleep(0.1)
        if pid is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            end = time.monotonic() + 3
            while time.monotonic() < end and group_alive(pid):
                await asyncio.sleep(0.05)
            gone = not group_alive(pid)
    finally:
        if pid is not None and group_alive(pid):
            os.killpg(pid, signal.SIGKILL)
        shutil.rmtree(work, ignore_errors=True)
    check("cancel-kills-foreign-uid-group", gone, "process group still alive after cancel")

    if FAILURES:
        print(f"FAILED: {', '.join(FAILURES)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
