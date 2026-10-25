"""Start/stop the local API, worker and frontend without opening console windows.

Uses the existing .env and virtualenv. PostgreSQL can be provided by Docker or
the optional portable runtime already prepared in runtime/postgres on Windows.
No downloads, external LLM configuration or system services are installed here.
"""

import argparse
import ctypes
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
STATE = RUNTIME / "dev-processes.json"
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
URL = "http://127.0.0.1:5173"


def process_stamp(pid):
    if os.name != "nt":
        try:
            return Path(f"/proc/{pid}/stat").read_text().split()[21]
        except (OSError, IndexError):
            return None
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return None
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def short_path(path):
    if os.name != "nt":
        return str(path)
    buffer = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if result else str(path)


def port_ready(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def check_http(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def wait_http(url):
    for _ in range(60):
        if check_http(url):
            return
        time.sleep(0.5)
    raise RuntimeError("Service did not become ready; inspect runtime/dev-*.log")


def spawn(name, args, state):
    stdout = (RUNTIME / f"dev-{name}.log").open("a", encoding="utf-8")
    stderr = (RUNTIME / f"dev-{name}-error.log").open("a", encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    try:
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, **options)
    finally:
        stdout.close()
        stderr.close()
    state["processes"].append({"name": name, "pid": process.pid, "stamp": process_stamp(process.pid)})
    save_state(state)


def save_state(state):
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def read_state():
    if not STATE.exists():
        return {"root": str(ROOT), "processes": [], "postgres_started": False}
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if Path(state["root"]).resolve() != ROOT:
        raise RuntimeError("Process state belongs to a different checkout")
    return state


def stop(state):
    for process in reversed(state["processes"]):
        if process["stamp"] and process_stamp(process["pid"]) == process["stamp"]:
            try:
                os.kill(process["pid"], signal.SIGTERM)
            except ProcessLookupError:
                pass
    if state.get("postgres_started"):
        pg_ctl = ROOT / "runtime/postgres/pgsql/bin/pg_ctl.exe"
        data = ROOT / "runtime/postgres-data"
        subprocess.run([short_path(pg_ctl), "-D", short_path(data), "-m", "fast", "-w", "stop"], check=True)
    state["processes"] = []
    state["postgres_started"] = False
    save_state(state)
    print("Project services stopped. Database files are preserved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-seed", action="store_true")
    args = parser.parse_args()
    if not PYTHON.exists():
        raise RuntimeError("Run uv sync --frozen to create .venv first")
    if Path(sys.prefix).resolve() != VENV.resolve():
        raise SystemExit(subprocess.call([str(PYTHON), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT))
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    RUNTIME.mkdir(exist_ok=True)
    state = read_state()
    if args.stop:
        stop(state)
        return
    if args.status:
        print("API:", "ready" if check_http("http://127.0.0.1:8000/health/ready") else "unavailable")
        print("Frontend:", "ready" if check_http(URL) else "unavailable")
        for process in state["processes"]:
            print(process["name"] + ":", "running" if process["stamp"] and process_stamp(process["pid"]) == process["stamp"] else "stopped")
        return
    if not (ROOT / ".env").exists():
        raise RuntimeError("Create .env from .env.example and configure the local database first")
    from backend.app.config import get_settings

    db = urlsplit(get_settings().database_url.get_secret_value())
    host, port = db.hostname or "127.0.0.1", db.port or 5432
    if not port_ready(host, port):
        pg_ctl = RUNTIME / "postgres/pgsql/bin/pg_ctl.exe"
        data = RUNTIME / "postgres-data"
        if host not in {"127.0.0.1", "localhost"} or not pg_ctl.exists() or not (data / "PG_VERSION").exists():
            raise RuntimeError("Start PostgreSQL (docker compose up -d db) and verify DATABASE_URL")
        subprocess.run([short_path(pg_ctl), "-D", short_path(data), "-l", short_path(RUNTIME) + "/postgres.log", "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"], check=True)
        state["postgres_started"] = True
        save_state(state)
    subprocess.run([str(PYTHON), "-X", "utf8", "-m", "backend.manage", "migrate"], check=True)
    if not args.no_seed:
        subprocess.run([str(PYTHON), "-X", "utf8", "-m", "backend.manage", "seed-demo"], check=True)
    if not port_ready("127.0.0.1", 8000):
        spawn("api", [str(PYTHON), "-X", "utf8", "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], state)
    wait_http("http://127.0.0.1:8000/health/ready")
    if not any(process["name"] == "worker" and process["stamp"] and process_stamp(process["pid"]) == process["stamp"] for process in state["processes"]):
        spawn("worker", [str(PYTHON), "-X", "utf8", "-m", "backend.worker"], state)
    if not port_ready("127.0.0.1", 5173):
        node = shutil.which("node")
        bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
        node = node or (str(bundled) if bundled.exists() else None)
        vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
        if not node or not vite.exists():
            raise RuntimeError("Install Node.js and run pnpm install --frozen-lockfile in frontend")
        spawn("frontend", [node, str(vite), str(ROOT / "frontend"), "--config", str(ROOT / "frontend/vite.config.ts")], state)
    wait_http(URL)
    print("Website:", URL)
    print("API: http://127.0.0.1:8000/docs")
    print("Stop: python scripts/dev.py --stop")


if __name__ == "__main__":
    main()
