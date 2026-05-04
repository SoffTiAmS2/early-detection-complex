#!/usr/bin/env python3
"""Start Cowrie and the EDC sidecar agents inside one sensor container."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


STOP = False


def mark_stop(*_: object) -> None:
    global STOP
    STOP = True


def cowrie_command() -> list[str]:
    candidates = [
        ["cowrie", "start", "-n"],
        ["/cowrie/cowrie-git/bin/cowrie", "start", "-n"],
    ]
    for command in candidates:
        executable = command[0]
        if "/" not in executable:
            return command
        if Path(executable).exists():
            return command
    return candidates[0]


def start_process(name: str, command: list[str]) -> subprocess.Popen[str]:
    print(f"edc-sensor: starting {name}: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, text=True)


def main() -> int:
    global STOP
    signal.signal(signal.SIGTERM, mark_stop)
    signal.signal(signal.SIGINT, mark_stop)

    os.environ.setdefault("HONEYPOT_LOG_PATH", "/cowrie/cowrie-git/var/log/cowrie/cowrie.json")
    processes = [
        start_process("cowrie", cowrie_command()),
        start_process("log-agent", ["python3", "/opt/edc/runtime/log_agent.py"]),
        start_process("display-agent", ["python3", "/opt/edc/runtime/display_agent.py"]),
    ]

    while not STOP:
        for process in processes:
            code = process.poll()
            if code is not None:
                print(f"edc-sensor: process exited: pid={process.pid} code={code}", flush=True)
                STOP = True
                break
        time.sleep(1)

    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
