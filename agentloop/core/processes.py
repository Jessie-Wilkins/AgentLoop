from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import threading
import time
from pathlib import Path
from typing import Callable


def run_interruptible(
    command: str | list[str],
    *,
    cwd: Path,
    shell: bool = False,
    stop_file: Path | None = None,
    poll_interval: float = 0.2,
    output_callback: Callable[[str], None] | None = None,
    heartbeat_interval: float | None = None,
    heartbeat_callback: Callable[[float], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    # AgentLoop intentionally executes trusted local workflow commands.
    process = subprocess.Popen(  # nosec B602
        command,
        cwd=cwd,
        shell=shell,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    output_parts: list[str] = []

    def read_output() -> None:
        if process.stdout is None:
            return
        try:
            for chunk in process.stdout:
                output_parts.append(chunk)
                if output_callback is not None:
                    output_callback(chunk)
        finally:
            process.stdout.close()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    stop_requested = False
    started_at = time.monotonic()
    last_heartbeat = started_at
    while process.poll() is None:
        if stop_file is not None and stop_file.exists():
            stop_requested = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            break
        now = time.monotonic()
        if heartbeat_interval is not None and heartbeat_callback is not None and now - last_heartbeat >= heartbeat_interval:
            heartbeat_callback(now - started_at)
            last_heartbeat = now
        time.sleep(poll_interval)

    if stop_requested:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    reader.join(timeout=2)
    if reader.is_alive() and process.poll() is None:
        process.kill()
        reader.join(timeout=2)
    output = "".join(output_parts)
    return subprocess.CompletedProcess(command, process.returncode or 0, output, None)
