from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence

from .config import AppPaths


class ProcessManager:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths()
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)

    def _pid_path(self, name: str) -> Path:
        return self.paths.state_dir / f"{name}.pid"

    def _log_path(self, name: str) -> Path:
        return self.paths.state_dir / f"{name}.log"

    def _read_pid(self, name: str) -> int | None:
        path = self._pid_path(name)
        try:
            return int(path.read_text(encoding="ascii").strip())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Could not read {name} process ID from {path}: {exc}") from exc

    @staticmethod
    def _matches(pid: int, marker: str) -> bool:
        try:
            command_line = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return False
        return marker.encode() in command_line

    def is_running(self, name: str, marker: str) -> bool:
        pid = self._read_pid(name)
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            self._pid_path(name).unlink(missing_ok=True)
            return False
        except PermissionError:
            return True
        if self._matches(pid, marker):
            return True
        self._pid_path(name).unlink(missing_ok=True)
        return False

    def start(
        self,
        name: str,
        command: Sequence[str],
        marker: str,
        env: Mapping[str, str] | None = None,
    ) -> int:
        if self.is_running(name, marker):
            return self._read_pid(name) or 0

        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            with self._log_path(name).open("ab") as log_file:
                process = subprocess.Popen(
                    list(command),
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=dict(env) if env is not None else None,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as exc:
            raise RuntimeError(f"Could not start {name}: {exc}") from exc
        self._pid_path(name).write_text(f"{process.pid}\n", encoding="ascii")
        return process.pid

    def stop(self, name: str, marker: str, timeout: float = 10.0) -> bool:
        if not self.is_running(name, marker):
            return False
        pid = self._read_pid(name)
        if pid is None:
            return False
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            self._pid_path(name).unlink(missing_ok=True)
            return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._matches(pid, marker):
                self._pid_path(name).unlink(missing_ok=True)
                return True
            time.sleep(0.1)

        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self._pid_path(name).unlink(missing_ok=True)
        return True

    def log_tail(self, name: str, line_count: int = 30) -> str:
        try:
            lines = self._log_path(name).read_text(encoding="utf-8", errors="replace").splitlines()
        except FileNotFoundError:
            return "(no log file)"
        except OSError as exc:
            return f"(could not read log: {exc})"
        return "\n".join(lines[-line_count:])
