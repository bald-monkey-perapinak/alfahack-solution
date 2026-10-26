"""Run the API and its queue worker in one Render Free web service."""

import os
import signal
import subprocess
import sys
import time


def main() -> int:
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
            "--no-access-log",
        ]
    )
    initializer = subprocess.Popen([sys.executable, "-m", "backend.initialize"])
    worker = None
    children = [api, initializer]
    try:
        while not stopping:
            api_code = api.poll()
            if api_code is not None:
                return api_code
            init_code = initializer.poll()
            if init_code is not None:
                if init_code != 0:
                    print(f"Database initialization exited with code {init_code}", flush=True)
                    return init_code
                if worker is None:
                    worker = subprocess.Popen([sys.executable, "-m", "backend.worker"])
                    children.append(worker)
            if worker is not None:
                worker_code = worker.poll()
                if worker_code is not None:
                    print(f"Queue worker exited unexpectedly with code {worker_code}", flush=True)
                    return worker_code or 1
            time.sleep(0.5)
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            if child.poll() is None:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
