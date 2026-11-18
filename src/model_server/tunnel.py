from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request

from .config import AppPaths, ConfigStore
from .processes import ProcessManager
from .server import LocalServer


TUNNEL_MARKER = "cloudflared"


class CloudflareTunnel:
    def __init__(
        self,
        paths: AppPaths | None = None,
        config_store: ConfigStore | None = None,
        process_manager: ProcessManager | None = None,
        local_server: LocalServer | None = None,
    ) -> None:
        self.paths = paths or AppPaths()
        self.config_store = config_store or ConfigStore(self.paths)
        self.processes = process_manager or ProcessManager(self.paths)
        self.local_server = local_server or LocalServer(self.paths, self.config_store, self.processes)

    def is_running(self) -> bool:
        return self.processes.is_running("cloudflared", TUNNEL_MARKER)

    def start(self) -> None:
        executable = shutil.which("cloudflared")
        if executable is None:
            raise RuntimeError(
                "cloudflared was not found. Install Cloudflare's cloudflared binary and ensure it is on PATH."
            )

        token = self.config_store.load_tunnel_token()
        self.local_server.start()
        config = self.config_store.load()
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{config.proxy_port}/health",
                timeout=2,
            ) as response:
                if response.status != 401:
                    raise RuntimeError("The authenticated model proxy did not respond as expected.")
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise RuntimeError(f"The authenticated model proxy is unavailable: {exc}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"The authenticated model proxy is unavailable: {exc}") from exc

        if not self.is_running():
            self.processes.start(
                "cloudflared",
                [
                    executable,
                    "tunnel",
                    "run",
                    "--token-file",
                    str(self.paths.tunnel_token_file),
                ],
                TUNNEL_MARKER,
                env=os.environ.copy(),
            )

    def stop(self) -> bool:
        return self.processes.stop("cloudflared", TUNNEL_MARKER)
