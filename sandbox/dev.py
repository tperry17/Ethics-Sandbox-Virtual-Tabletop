"""Run the Python server and TypeScript watcher together."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _signal(process: subprocess.Popen[bytes], *, force: bool) -> None:
    """Stop a child and, outside Windows, the process group it leads."""
    if sys.platform == "win32":
        if force:
            process.kill()
        else:
            process.terminate()
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)


def _stop(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop child processes cleanly."""
    for process in processes:
        if process.poll() is None:
            _signal(process, force=False)
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _signal(process, force=True)


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
                "--reload-dir",
                "content",
                # Uvicorn watches only *.py unless told otherwise; game
                # definitions and the content they name are YAML and CSV.
                "--reload-include",
                "*.yaml",
                "--reload-include",
                "*.csv",
            ],
            cwd=PROJECT_ROOT,
            start_new_session=True,
        ),
        subprocess.Popen(
            [shutil.which("npm") or "npm", "run", "dev"],
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
