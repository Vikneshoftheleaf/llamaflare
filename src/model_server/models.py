from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .config import AppPaths


DEFAULT_MODEL_REPOSITORY = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
DEFAULT_MODEL_FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class ModelFile:
    path: Path

    @property
    def relative_path(self) -> str:
        return self.path.as_posix()

    @property
    def display_name(self) -> str:
        return f"{self.path.name} ({self.path.parent.name})"


def list_models(paths: AppPaths | None = None) -> list[ModelFile]:
    model_dir = (paths or AppPaths()).models_dir
    if not model_dir.exists():
        return []
    return [
        ModelFile(path=path.resolve())
        for path in sorted(model_dir.rglob("*.gguf"))
        if path.is_file()
    ]


def model_path_from_config(relative_path: str | None, paths: AppPaths | None = None) -> Path | None:
    if not relative_path:
        return None
    app_paths = paths or AppPaths()
    model_dir = app_paths.models_dir.resolve()
    candidate = (app_paths.repository_root / relative_path).resolve()
    if not candidate.is_relative_to(model_dir):
        raise ValueError("The configured model must be located inside this repository's models directory.")
    return candidate


def model_relative_path(model_path: Path, paths: AppPaths | None = None) -> str:
    app_paths = paths or AppPaths()
    return model_path.resolve().relative_to(app_paths.repository_root.resolve()).as_posix()


def _validate_download_request(repository_id: str, filename: str) -> None:
    repository_parts = repository_id.split("/")
    if (
        not REPOSITORY_PATTERN.fullmatch(repository_id)
        or len(repository_parts) != 2
        or any(part in {"", ".", ".."} for part in repository_parts)
    ):
        raise ValueError("Use a Hugging Face model ID in the form owner/repository.")
    if (
        Path(filename).name != filename
        or "\\" in filename
        or "/" in filename
        or not filename.lower().endswith(".gguf")
    ):
        raise ValueError("Choose a single GGUF filename without directory components.")


def download_model(
    repository_id: str,
    filename: str,
    paths: AppPaths | None = None,
) -> Path:
    _validate_download_request(repository_id, filename)
    app_paths = paths or AppPaths()
    destination = app_paths.models_dir / repository_id.replace("/", "--")
    destination.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import hf_hub_download

    downloaded_path = Path(
        hf_hub_download(
            repo_id=repository_id,
            filename=filename,
            local_dir=destination,
        )
    ).resolve()
    model_dir = app_paths.models_dir.resolve()
    if not downloaded_path.is_relative_to(model_dir):
        raise RuntimeError("The model downloader returned a path outside the repository models directory.")
    return downloaded_path
