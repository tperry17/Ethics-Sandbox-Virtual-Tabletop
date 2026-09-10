"""Run the Python server and TypeScript watcher together."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop child processes cleanly."""
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def main() -> None:
    """Start Uvicorn and the Vite client watcher until either exits."""
    processes = [
        subprocess.Popen(
            [
                "uvicorn",
                "sandbox.web.app:app",
                "--reload",
                "--reload-dir",
                "sandbox",
            ],
            cwd=PROJECT_ROOT,
            start_new_session=True,
        ),
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=PROJECT_ROOT,
            start_new_session=True,
        ),
    ]
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        _stop(processes)


if __name__ == "__main__":
    main()
