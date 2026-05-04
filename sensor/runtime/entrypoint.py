#!/usr/bin/env python3
"""Start Cowrie and the EDC sidecar agents inside one sensor container."""

from __future__ import annotations

import os
import shutil
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
        ["twistd", "-n", "cowrie"],
        ["/cowrie/cowrie-env/bin/twistd", "-n", "cowrie"],
        ["cowrie", "start"],
        ["/cowrie/cowrie-git/bin/cowrie", "start"],
    ]
    for command in candidates:
        executable = command[0]
        if "/" not in executable:
            if shutil.which(executable):
                return command
            continue
        if Path(executable).exists():
            return command
    return candidates[0]


def find_command(*names: str) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        path = Path(name)
        if path.exists():
            return str(path)
    return None


def prepare_cowrie_filesystem() -> None:
    output = Path("/tmp/edc-cowrie/fs.pickle")
    honeyfs = Path("/cowrie/cowrie-git/src/cowrie/data/honeyfs")
    output.parent.mkdir(parents=True, exist_ok=True)
    createfs = find_command("createfs", "/cowrie/cowrie-git/bin/createfs")
    if not createfs:
        copy_default_filesystem(output)
        return
    command = [createfs, "-l", str(honeyfs), "-d", "6", "-o", str(output)]
    print(f"edc-sensor: generating Cowrie filesystem: {' '.join(command)}", flush=True)
    result = subprocess.run(command, check=False)
    if result.returncode != 0 or not output.exists():
        print("edc-sensor: createfs failed; falling back to Cowrie default filesystem", flush=True)
        copy_default_filesystem(output)


def copy_default_filesystem(output: Path) -> None:
    candidates = [
        Path("/cowrie/cowrie-git/src/cowrie/data/fs.pickle"),
        Path("/cowrie/cowrie-git/share/cowrie/fs.pickle"),
    ]
    for source in candidates:
        if source.exists():
            shutil.copyfile(source, output)
            print(f"edc-sensor: using default Cowrie filesystem: {source}", flush=True)
            return
    print("edc-sensor: no Cowrie filesystem source found; startup may fail", flush=True)


def start_process(name: str, command: list[str]) -> subprocess.Popen[str]:
    print(f"edc-sensor: starting {name}: {' '.join(command)}", flush=True)
    return subprocess.Popen(command, text=True)


def main() -> int:
    global STOP
    signal.signal(signal.SIGTERM, mark_stop)
    signal.signal(signal.SIGINT, mark_stop)

    os.environ.setdefault("HONEYPOT_LOG_PATH", "/cowrie/cowrie-git/var/log/cowrie/cowrie.json")
    prepare_cowrie_filesystem()
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
