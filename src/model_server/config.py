from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppPaths:
    repository_root: Path = REPOSITORY_ROOT
    config_home: Path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    state_home: Path = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))

    @property
    def models_dir(self) -> Path:
        return self.repository_root / "models"

    @property
    def config_dir(self) -> Path:
        return self.config_home / "model-server"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def tunnel_token_file(self) -> Path:
        return self.config_dir / "cloudflare-token"

    @property
    def state_dir(self) -> Path:
        return self.state_home / "model-server"


@dataclass
class AppConfig:
    selected_model: str | None = None
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    proxy_port: int = 8081
    api_key: str = ""


class ConfigStore:
    def __init__(self, paths: AppPaths | None = None) -> None:
        self.paths = paths or AppPaths()

    def load(self) -> AppConfig:
        path = self.paths.config_file
        if not path.exists():
            return AppConfig()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return AppConfig(**data)
        except (OSError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Could not read configuration at {path}: {exc}") from exc

    def save(self, config: AppConfig) -> None:
        directory = self.paths.config_dir
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        path = self.paths.config_file
        temporary_path = path.with_suffix(".json.tmp")
        try:
            temporary_path.write_text(
                json.dumps(asdict(config), indent=2) + "\n",
                encoding="utf-8",
            )
            os.chmod(temporary_path, 0o600)
            temporary_path.replace(path)
        except OSError as exc:
            raise RuntimeError(f"Could not save configuration at {path}: {exc}") from exc

    def save_tunnel_token(self, token: str) -> None:
        if not token.strip():
            raise ValueError("The Cloudflare tunnel token cannot be empty.")
        directory = self.paths.config_dir
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        path = self.paths.tunnel_token_file
        try:
            path.write_text(token.strip() + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
        except OSError as exc:
            raise RuntimeError(f"Could not save the Cloudflare token at {path}: {exc}") from exc

    def load_tunnel_token(self) -> str:
        try:
            token = self.paths.tunnel_token_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(
                "Cloudflare is not configured. Add a tunnel token in the Tunnel menu."
            ) from exc
        if not token:
            raise RuntimeError("The saved Cloudflare tunnel token is empty.")
        return token
