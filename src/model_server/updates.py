from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .config import AppPaths


@dataclass(frozen=True)
class UpdateStatus:
    message: str
    available: bool = False
    can_fast_forward: bool = False


class GitUpdater:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths()

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.paths.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"Git {' '.join(args)} failed: {message}")
        return result

    def check(self) -> UpdateStatus:
        if self._git("rev-parse", "--is-inside-work-tree", check=False).returncode:
            raise RuntimeError("The project directory is not a Git working tree.")

        upstream = self._git(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
            check=False,
        )
        if upstream.returncode:
            raise RuntimeError("This checkout has no upstream branch configured.")
        upstream_ref = upstream.stdout.strip()
        remote = upstream_ref.split("/", 1)[0]
        self._git("fetch", remote)

        counts = self._git("rev-list", "--left-right", "--count", f"HEAD...{upstream_ref}")
        ahead, behind = (int(value) for value in counts.stdout.split())
        if behind == 0:
            if ahead:
                return UpdateStatus(f"This checkout is {ahead} commit(s) ahead; no upstream updates are available.")
            return UpdateStatus("This checkout is up to date.")

        dirty = self._git("status", "--porcelain").stdout.strip()
        if dirty:
            return UpdateStatus(
                f"{behind} upstream update(s) are available, but local tracked changes prevent a safe update.",
                available=True,
            )
        if ahead:
            return UpdateStatus(
                f"The checkout has diverged ({ahead} local commit(s), {behind} upstream update(s)); "
                "a fast-forward update is not possible.",
                available=True,
            )
        return UpdateStatus(f"{behind} upstream update(s) are available.", available=True, can_fast_forward=True)

    def apply(self) -> str:
        self._git("merge", "--ff-only", "@{upstream}")
        return "Updated successfully. Restart the CLI; run `pip install -e .` if package dependencies changed."
