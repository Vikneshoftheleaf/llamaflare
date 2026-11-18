from __future__ import annotations

import os
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import AppConfig, AppPaths, ConfigStore
from .models import model_path_from_config
from .processes import ProcessManager


LLAMA_MARKER = "llama-server"
PROXY_MARKER = "model_server.proxy"


class LocalServer:
    def __init__(
        self,
        paths: AppPaths | None = None,
        config_store: ConfigStore | None = None,
        process_manager: ProcessManager | None = None,
    ) -> None:
        self.paths = paths or AppPaths()
        self.config_store = config_store or ConfigStore(self.paths)
        self.processes = process_manager or ProcessManager(self.paths)

    def _health(self, port: int, expected_status: int = 200) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                return response.status == expected_status
        except urllib.error.HTTPError as exc:
            return exc.code == expected_status
        except (OSError, urllib.error.URLError):
            return False

    def _wait_until_ready(
        self,
        name: str,
        marker: str,
        port: int,
        timeout: float = 180.0,
        expected_status: int = 200,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._health(port, expected_status):
                return
            if not self.processes.is_running(name, marker):
                log = self.processes.log_tail(name)
                raise RuntimeError(f"{name} exited before becoming ready. Recent log output:\n{log}")
            time.sleep(0.5)
        raise RuntimeError(
            f"{name} did not become ready within {int(timeout)} seconds. "
            f"Recent log output:\n{self.processes.log_tail(name)}"
        )

    def is_running(self) -> bool:
        return self.processes.is_running("llama-server", LLAMA_MARKER)

    def start(self) -> None:
        config = self.config_store.load()
        model_path = model_path_from_config(config.selected_model, self.paths)
        if model_path is None or not model_path.is_file():
            raise RuntimeError("Select or download a GGUF model before starting the local server.")

        executable = shutil.which("llama-server")
        if executable is None:
            raise RuntimeError(
                "llama-server was not found. Install/build llama.cpp and ensure llama-server is on PATH."
            )

        if not config.api_key:
            config.api_key = secrets.token_urlsafe(32)
            self.config_store.save(config)

        if not self.is_running():
            self.processes.start(
                "llama-server",
                [
                    executable,
                    "--model",
                    str(model_path),
                    "--host",
                    config.server_host,
                    "--port",
                    str(config.server_port),
                    "--n-gpu-layers",
                    "99",
                ],
                LLAMA_MARKER,
            )
        self._wait_until_ready("llama-server", LLAMA_MARKER, config.server_port)

        proxy_env = os.environ.copy()
        proxy_env.update(
            {
                "MODEL_SERVER_API_KEY": config.api_key,
                "MODEL_SERVER_UPSTREAM": f"http://{config.server_host}:{config.server_port}",
                "MODEL_SERVER_PROXY_PORT": str(config.proxy_port),
            }
        )
        if not self.processes.is_running("model-server-proxy", PROXY_MARKER):
            self.processes.start(
                "model-server-proxy",
                [sys.executable, "-m", "model_server.proxy"],
                PROXY_MARKER,
                env=proxy_env,
            )
        self._wait_until_ready(
            "model-server-proxy",
            PROXY_MARKER,
            config.proxy_port,
            timeout=30.0,
            expected_status=401,
        )

    def stop(self) -> bool:
        proxy_stopped = self.processes.stop("model-server-proxy", PROXY_MARKER)
        server_stopped = self.processes.stop("llama-server", LLAMA_MARKER)
        return proxy_stopped or server_stopped

    def local_url(self) -> str:
        config = self.config_store.load()
        return f"http://{config.server_host}:{config.server_port}/v1"

    def tunnel_url(self) -> str:
        config = self.config_store.load()
        return f"http://127.0.0.1:{config.proxy_port}"

    def ensure_api_key(self) -> str:
        config: AppConfig = self.config_store.load()
        if not config.api_key:
            config.api_key = secrets.token_urlsafe(32)
            self.config_store.save(config)
        return config.api_key
