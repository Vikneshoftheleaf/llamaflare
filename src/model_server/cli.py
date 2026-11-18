from __future__ import annotations

import sys
from pathlib import Path

from prompt_toolkit.shortcuts import (
    input_dialog,
    message_dialog,
    radiolist_dialog,
    yes_no_dialog,
)

from . import __version__
from .chat import chat_loop
from .config import AppConfig, AppPaths, ConfigStore
from .models import (
    DEFAULT_MODEL_FILE,
    DEFAULT_MODEL_REPOSITORY,
    download_model,
    list_models,
    model_path_from_config,
    model_relative_path,
)
from .server import LocalServer
from .tunnel import CloudflareTunnel
from .updates import GitUpdater


def _show_message(title: str, text: str) -> None:
    message_dialog(title=title, text=text).run()


def _selected_model(paths: AppPaths, store: ConfigStore) -> Path | None:
    config = store.load()
    path = model_path_from_config(config.selected_model, paths)
    return path if path is not None and path.is_file() else None


def _download(
    repository_id: str,
    filename: str,
    paths: AppPaths,
    store: ConfigStore,
    server: LocalServer,
) -> None:
    try:
        model_path = download_model(repository_id, filename, paths)
        config = store.load()
        new_selection = model_relative_path(model_path, paths)
        if config.selected_model != new_selection and server.is_running():
            server.stop()
        config.selected_model = new_selection
        store.save(config)
        _show_message("Model ready", f"Downloaded and selected:\n{model_path.name}")
    except Exception as exc:
        _show_message("Download failed", str(exc))


def _model_menu(paths: AppPaths, store: ConfigStore, server: LocalServer) -> None:
    while True:
        choices = [
            ("select", "Select an installed model"),
            ("default", f"Download default model: {DEFAULT_MODEL_REPOSITORY}"),
            ("download", "Download a GGUF model from Hugging Face"),
            ("back", "Back"),
        ]
        selection = radiolist_dialog(title="Models", text="Choose a model action:", values=choices).run()
        if selection in (None, "back"):
            return
        if selection == "select":
            models = list_models(paths)
            if not models:
                _show_message("No models found", f"Download a GGUF model into:\n{paths.models_dir}")
                continue
            current = store.load().selected_model
            choices = [
                (model.relative_path, f"{model.display_name}{'  [selected]' if model.relative_path == current else ''}")
                for model in models
            ]
            selected = radiolist_dialog(
                title="Select model",
                text="Downloaded models are stored inside the repository:",
                values=choices,
            ).run()
            if selected:
                config = store.load()
                if config.selected_model != selected and server.is_running():
                    server.stop()
                config.selected_model = selected
                store.save(config)
                _show_message("Model selected", selected)
        elif selection == "default":
            _download(DEFAULT_MODEL_REPOSITORY, DEFAULT_MODEL_FILE, paths, store, server)
        elif selection == "download":
            repository_id = input_dialog(
                title="Hugging Face model",
                text="Model repository ID (owner/repository):",
            ).run()
            if not repository_id:
                continue
            filename = input_dialog(
                title="GGUF file",
                text="Exact GGUF filename to download:",
                default="model-q4_k_m.gguf",
            ).run()
            if filename:
                _download(repository_id.strip(), filename.strip(), paths, store, server)


def _local_menu(server: LocalServer, paths: AppPaths, store: ConfigStore) -> None:
    while True:
        is_running = server.is_running()
        config = store.load()
        model_path = model_path_from_config(config.selected_model, paths)
        status = "running" if is_running else "stopped"
        model_name = model_path.name if model_path and model_path.exists() else "none selected"
        selection = radiolist_dialog(
            title="Local server",
            text=f"Status: {status}\nModel: {model_name}\nLocal API: {server.local_url()}",
            values=[
                ("start", "Start local model server"),
                ("stop", "Stop local model server and proxy"),
                ("back", "Back"),
            ],
        ).run()
        if selection in (None, "back"):
            return
        try:
            if selection == "start":
                server.start()
                _show_message(
                    "Server started",
                    f"Local OpenAI-compatible API:\n{server.local_url()}\n\n"
                    f"Authenticated tunnel proxy:\n{server.tunnel_url()}",
                )
            else:
                stopped = server.stop()
                _show_message("Local server", "Server stopped." if stopped else "Server was not running.")
        except Exception as exc:
            _show_message("Local server error", str(exc))


def _tunnel_menu(tunnel: CloudflareTunnel, server: LocalServer, store: ConfigStore) -> None:
    while True:
        token_configured = tunnel.paths.tunnel_token_file.exists()
        status = "running" if tunnel.is_running() else "stopped"
        selection = radiolist_dialog(
            title="Cloudflare Tunnel",
            text=(
                f"Status: {status}\nToken: {'configured' if token_configured else 'not configured'}\n"
                f"Tunnel target: {server.tunnel_url()}\n"
                "Set the Cloudflare public hostname's service to this target."
            ),
            values=[
                ("configure", "Configure named tunnel token"),
                ("start", "Start tunnel"),
                ("stop", "Stop tunnel"),
                ("key", "Show API bearer token"),
                ("back", "Back"),
            ],
        ).run()
        if selection in (None, "back"):
            return
        try:
            if selection == "configure":
                token = input_dialog(
                    title="Cloudflare Tunnel token",
                    text="Paste the token for your Cloudflare named tunnel:",
                    password=True,
                ).run()
                if token:
                    tunnel.config_store.save_tunnel_token(token)
                    _show_message("Tunnel configured", "Token saved with owner-only file permissions.")
            elif selection == "start":
                if not yes_no_dialog(
                    title="Start public tunnel",
                    text=(
                        f"Make sure your Cloudflare public hostname forwards to {server.tunnel_url()}.\n"
                        "Requests to the public model API will require the bearer token."
                    ),
                ).run():
                    continue
                tunnel.start()
                _show_message("Tunnel started", "cloudflared is running. Check its log if the hostname is not reachable.")
            elif selection == "stop":
                stopped = tunnel.stop()
                _show_message("Tunnel", "Tunnel stopped." if stopped else "Tunnel was not running.")
            elif selection == "key":
                api_key = server.ensure_api_key()
                _show_message(
                    "API bearer token",
                    f"Copy this token into the Authorization header:\n\nBearer {api_key}\n\n"
                    "Treat it like a password. It is stored locally with owner-only permissions.",
                )
        except Exception as exc:
            _show_message("Tunnel error", str(exc))


def _updates_menu(updater: GitUpdater) -> None:
    try:
        status = updater.check()
        if not status.available:
            _show_message("Git updates", status.message)
            return
        if not status.can_fast_forward:
            _show_message("Git updates", status.message)
            return
        if yes_no_dialog(
            title="Git updates available",
            text=f"{status.message}\n\nApply with a safe fast-forward?",
        ).run():
            _show_message("Git update", updater.apply())
    except Exception as exc:
        _show_message("Git update failed", str(exc))


def _chat_action(server: LocalServer, store: ConfigStore) -> None:
    if not server.is_running():
        _show_message("Model server is stopped", "Start the local server before opening chat.")
        return
    try:
        config: AppConfig = store.load()
        chat_loop(server.local_url(), config.api_key)
    except Exception as exc:
        _show_message("Chat failed", str(exc))


def _first_run(paths: AppPaths, store: ConfigStore, server: LocalServer) -> None:
    if list_models(paths) or paths.config_file.exists():
        return
    if yes_no_dialog(
        title="First-run setup",
        text=(
            f"Download the default sub-1B model ({DEFAULT_MODEL_REPOSITORY})?\n"
            "The GGUF file will be stored in this repository's models/ directory."
        ),
    ).run():
        _download(DEFAULT_MODEL_REPOSITORY, DEFAULT_MODEL_FILE, paths, store, server)


def run_interactive() -> None:
    paths = AppPaths()
    store = ConfigStore(paths)
    server = LocalServer(paths, store)
    tunnel = CloudflareTunnel(paths, store, local_server=server)
    updater = GitUpdater(paths)
    _first_run(paths, store, server)

    while True:
        config = store.load()
        selected = _selected_model(paths, store)
        local_status = "on" if server.is_running() else "off"
        tunnel_status = "on" if tunnel.is_running() else "off"
        model_name = selected.name if selected else "none"
        selection = radiolist_dialog(
            title=f"Model Server v{__version__}",
            text=f"Model: {model_name}  |  Local server: {local_status}  |  Tunnel: {tunnel_status}",
            values=[
                ("chat", "Chat with the local model"),
                ("models", "Select or download models"),
                ("local", "Set up local server"),
                ("tunnel", "Set up Cloudflare Tunnel"),
                ("updates", "Look for Git updates"),
                ("exit", "Exit"),
            ],
        ).run()
        if selection in (None, "exit"):
            return
        if selection == "chat":
            _chat_action(server, store)
        elif selection == "models":
            _model_menu(paths, store, server)
        elif selection == "local":
            _local_menu(server, paths, store)
        elif selection == "tunnel":
            _tunnel_menu(tunnel, server, store)
        elif selection == "updates":
            _updates_menu(updater)


def main() -> None:
    if "--version" in sys.argv[1:]:
        print(__version__)
        return
    try:
        run_interactive()
    except (KeyboardInterrupt, EOFError):
        print()
    except Exception as exc:
        print(f"model-server: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
