"""Portable launcher that finds a Python 3.11+ interpreter and runs bootstrap."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from typing import Iterable, Optional


def _version_ok(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command + ["-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return False
    try:
        major, minor = [int(part) for part in result.stdout.strip().split(".")]
    except Exception:
        return False
    return (major, minor) >= (3, 11)


def _candidate_commands() -> Iterable[str]:
    env_python = os.environ.get("EM_RAG_PYTHON")
    if env_python:
        yield env_python
    yield sys.executable
    if os.name == "nt":
        yield "py -3.11"
        yield "python"
        yield "python3"
    else:
        yield "python3.11"
        yield "python3"
        yield "python"


def _split_command(command: str) -> list[str]:
    return shlex.split(command)


def _find_bootstrap_python() -> Optional[list[str]]:
    seen = set()
    for command in _candidate_commands():
        parts = _split_command(command)
        if not parts:
            continue
        key = tuple(parts)
        if key in seen:
            continue
        seen.add(key)
        exe = parts[0]
        if shutil.which(exe) and _version_ok(parts):
            return parts
    return None


def main() -> int:
    command = _find_bootstrap_python()
    if not command:
        print("未找到可用的 Python 3.11+ 解释器")
        return 1
    if command[0] == sys.executable and len(command) == 1:
        from em_rag.bootstrap import main as bootstrap_main

        return bootstrap_main()
    return subprocess.call(command + ["-m", "em_rag.bootstrap", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
