#!/usr/bin/env python3
"""
Cross-platform command-line interface for the tiny llama.cpp server.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
MODELS_FILE = ROOT / "models.conf"
STATE_DIR = ROOT / ".state"
MODELS_DIR = ROOT / "models"
LLAMA_DIR = ROOT / "llama.cpp"


def title(text: str) -> None:
    print()
    print("=" * 64)
    print(text.center(64))
    print("=" * 64)


def env_defaults() -> dict[str, str]:
    values: dict[str, str] = {
        "MODEL": "llama3.2-1b",
        "PORT": "8080",
        "CTX": "2048",
        "THREADS": "",
        "API_KEY": "",
    }
    if ENV_FILE.exists():
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def read_key() -> str:
    if platform.system() == "Windows":
        import msvcrt
        first = msvcrt.getch()
        if first in (b"\x00", b"\xe0"):
            second = msvcrt.getch()
            return {b"H": "up", b"P": "down", b"M": "right", b"K": "left"}.get(second, "")
        if first == b"\r":
            return "enter"
        if first == b"\x1b":
            return "escape"
        if first == b"\x03":
            return "interrupt"
        return first.decode("utf-8", errors="ignore")

    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = sys.stdin.read(1)
        if first == "\x1b":
            sequence = sys.stdin.read(2)
            return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(sequence, "escape")
        if first == "\r" or first == "\n":
            return "enter"
        if first == "\x03":
            return "interrupt"
        return first
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def arrow_menu(
    heading: str,
    options: list[str],
    hint: str = "Use Up/Down arrows, Enter to choose",
    initial_index: int = 0,
) -> int | None:
    selected = initial_index if options and 0 <= initial_index < len(options) else 0
    while True:
        sys.stdout.write("\033[2J\033[H")
        title(heading)
        for index, option in enumerate(options):
            marker = ">" if index == selected else " "
            style = "\033[7m" if index == selected else ""
            reset = "\033[0m" if index == selected else ""
            print(f"{style}{marker} {option:<58}{reset}")
        print()
        print(hint)
        sys.stdout.flush()

        key = read_key()
        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "enter":
            return selected
        elif key == "escape":
            return None
        elif key == "interrupt":
            raise KeyboardInterrupt


def llama_bin() -> tuple[Path, Path]:
    bin_dir = LLAMA_DIR / "build" / "bin"
    if platform.system() == "Windows":
        return bin_dir / "llama-cli.exe", bin_dir / "llama-server.exe"
    return bin_dir / "llama-cli", bin_dir / "llama-server"


def list_models() -> list[tuple[str, str, str]]:
    models: list[tuple[str, str, str]] = []
    if not MODELS_FILE.exists():
        return models
    for raw_line in MODELS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|", 2)]
        if len(parts) == 3:
            models.append((parts[0], parts[1], parts[2]))
    return models


def show_models() -> None:
    title("AVAILABLE MODELS")
    models = list_models()
    if not models:
        print("No models found in models.conf.")
        return
    for key, filename, _ in models:
        print(f"  {key:<18} {filename}")


def binary_ready() -> bool:
    cli, server = llama_bin()
    return cli.is_file() and server.is_file()


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}")
    urllib.request.urlretrieve(url, destination)
    print(f"Saved: {destination}")


def resolve_model(model: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    candidate = Path(model).expanduser()
    if candidate.is_file():
        print(f"==> Using local file {candidate}")
        return candidate.resolve()

    if model.startswith(("http://", "https://")):
        filename = model.split("?", 1)[0].rsplit("/", 1)[-1] or "model.gguf"
        destination = MODELS_DIR / filename
    else:
        match = next((item for item in list_models() if item[0] == model), None)
        if match is None:
            print(f"Unknown model '{model}'.")
            show_models()
            raise SystemExit(1)
        _, filename, url = match
        destination = MODELS_DIR / filename

    if destination.is_file() and destination.stat().st_size > 0:
        print(f"==> Model already downloaded: {destination}")
        return destination

    if model.startswith(("http://", "https://")):
        url = model
    else:
        url = next(item[2] for item in list_models() if item[0] == model)

    temp = destination.with_suffix(destination.suffix + ".part")
    print("==> Downloading model")
    try:
        download_file(url, temp)
        temp.replace(destination)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"Model download failed: {exc}") from exc
    return destination


def physical_threads() -> int:
    if os.cpu_count():
        return max(1, os.cpu_count())
    return 2


def save_pid(name: str, process: subprocess.Popen) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{name}.pid").write_text(str(process.pid), encoding="utf-8")


def read_pid(name: str) -> int | None:
    pid_file = STATE_DIR / f"{name}.pid"
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def stop_all() -> None:
    title("STOPPING SERVICES")
    stopped = False
    for name in ("tunnel", "server"):
        pid = read_pid(name)
        pid_file = STATE_DIR / f"{name}.pid"
        if pid is not None and process_running(pid):
            stopped = True
            try:
                if platform.system() == "Windows":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                else:
                    os.kill(pid, 15)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        pid_file.unlink(missing_ok=True)
    print("Stopped server and tunnel." if stopped else "No running services found.")


def wait_for_health(port: int, timeout: int = 180) -> bool:
    import urllib.error

    url = f"http://127.0.0.1:{port}/health"
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1)
    return False


def start_server(model_path: Path, ctx: int, threads: int, port: int, api_key: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _, server = llama_bin()
    command = [
        str(server),
        "-m",
        str(model_path),
        "-c",
        str(ctx),
        "-t",
        str(threads),
        "-np",
        "1",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    if api_key:
        command.extend(["--api-key", api_key])

    log_path = STATE_DIR / "server.log"
    with log_path.open("ab") as log:
        if platform.system() == "Windows":
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    save_pid("server", process)
    print("==> Starting llama-server")
    print(f"==> Loading model (ctx={ctx}, threads={threads})...")

    if not wait_for_health(port):
        print(f"Server failed to start. See {log_path}")
        raise SystemExit(1)


def chat(args: argparse.Namespace, defaults: dict[str, str]) -> None:
    if not binary_ready():
        print("llama.cpp is not built. Run Setup first.")
        raise SystemExit(1)
    cli, _ = llama_bin()
    model = args.model or defaults["MODEL"]
    ctx = args.ctx if args.ctx is not None else int(defaults["CTX"])
    threads = args.threads if args.threads is not None else int(defaults["THREADS"] or physical_threads())
    model_path = resolve_model(model)
    title("LLAMA.CPP CHAT")
    subprocess.run(
        [str(cli), "-m", str(model_path), "-c", str(ctx), "-t", str(threads), "-cnv"],
        cwd=ROOT,
    )


def serve(args: argparse.Namespace, defaults: dict[str, str]) -> None:
    if not binary_ready():
        print("llama.cpp is not built. Run Setup first.")
        raise SystemExit(1)
    model = args.model or defaults["MODEL"]
    port = args.port if args.port is not None else int(defaults["PORT"])
    ctx = args.ctx if args.ctx is not None else int(defaults["CTX"])
    threads = args.threads if args.threads is not None else int(defaults["THREADS"] or physical_threads())
    model_path = resolve_model(model)
    api_key = args.api_key or defaults["API_KEY"]
    start_server(model_path, ctx, threads, port, api_key)
    title("LOCAL SERVER")
    print(f"Web UI:  http://127.0.0.1:{port}")
    if api_key:
        print(f"API key: {api_key}")


def tunnel(args: argparse.Namespace, defaults: dict[str, str]) -> None:
    if not binary_ready():
        print("llama.cpp is not built. Run Setup first.")
        raise SystemExit(1)
    cloudflared = shutil.which("cloudflared")
    if not cloudflared:
        print("cloudflared was not found. Run setup first.")
        raise SystemExit(1)

    model = args.model or defaults["MODEL"]
    port = args.port if args.port is not None else int(defaults["PORT"])
    ctx = args.ctx if args.ctx is not None else int(defaults["CTX"])
    threads = args.threads if args.threads is not None else int(defaults["THREADS"] or physical_threads())
    api_key = args.api_key or defaults["API_KEY"]
    if not api_key:
        import secrets
        api_key = secrets.token_hex(16)
        with ENV_FILE.open("a", encoding="utf-8") as env:
            env.write(f"\nAPI_KEY={api_key}\n")

    model_path = resolve_model(model)
    start_server(model_path, ctx, threads, port, api_key)

    log_path = STATE_DIR / "tunnel.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [cloudflared, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=platform.system() != "Windows",
        )
    save_pid("tunnel", process)

    public_url = ""
    for _ in range(40):
        text = log_path.read_text(encoding="utf-8", errors="replace")
        import re
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
        if match:
            public_url = match.group(0)
            break
        time.sleep(1)

    title("PUBLIC TUNNEL")
    print(f"Public URL: {public_url or 'Not detected yet'}")
    print(f"API key:    {api_key}")
    print(f"Log:        {log_path}")


def direct_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tiny llama.cpp model server")
    sub = parser.add_subparsers(dest="command")

    setup = sub.add_parser("setup", help="build llama.cpp and install cloudflared")
    setup.add_argument("-u", "--update", action="store_true", help="update llama.cpp and rebuild")
    sub.add_parser("chat", help="open interactive terminal chat")
    sub.add_parser("serve", help="start local API and web UI")
    sub.add_parser("tunnel", help="start local server and Cloudflare tunnel")
    sub.add_parser("stop", help="stop server and tunnel")
    sub.add_parser("list", help="list configured models")

    for name in ("chat", "serve", "tunnel"):
        item = sub.choices[name]
        item.add_argument("-m", "--model")
        item.add_argument("-c", "--ctx", type=int)
        item.add_argument("-t", "--threads", type=int)
        item.add_argument("-p", "--port", type=int)
        if name == "serve":
            item.add_argument("-k", "--api-key")
        if name == "tunnel":
            item.add_argument("-k", "--api-key")
    return parser


def run_setup(update: bool = False) -> None:
    script = ROOT / ("setup.ps1" if platform.system() == "Windows" else "setup.sh")
    if platform.system() == "Windows":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        if update:
            command.append("-Update")
        subprocess.run(command, cwd=ROOT)
    else:
        command = ["bash", str(script)]
        if update:
            command.append("--update")
        subprocess.run(command, cwd=ROOT)


def set_env_value(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    found = False
    updated: list[str] = []
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            current_key = line.split("=", 1)[0].strip()
            if current_key == key:
                updated.append(f"{key}={value}")
                found = True
                continue
        updated.append(line)
    if not found:
        updated.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def choose_model(default: str) -> str | None:
    models = list_models()
    if not models:
        sys.stdout.write("\033[2J\033[H")
        title("MODEL CONFIG")
        print("No models found in models.conf.")
        input("\nPress Enter to continue...")
        return None

    options = [f"{key:<18} {filename}" for key, filename, _ in models]
    options.append("Cancel")
    default_index = next(
        (index for index, (key, _, _) in enumerate(models) if key == default),
        0,
    )

    choice = arrow_menu(
        "CHOOSE MODEL",
        options,
        "Use Up/Down arrows, Enter to choose, Esc to cancel",
        default_index,
    )
    if choice is None or choice == len(models):
        return None
    return models[choice][0]


def text_setting(prompt: str, default: str = "") -> str | None:
    sys.stdout.write("\033[2J\033[H")
    title("MODEL & SERVER SETTINGS")
    try:
        value = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return None
    return value or default


def configure_menu(defaults: dict[str, str]) -> None:
    while True:
        choices = [
            f"Model: {defaults['MODEL']}",
            f"Context size: {defaults['CTX']}",
            f"Threads: {defaults['THREADS'] or 'Auto'}",
            f"Server port: {defaults['PORT']}",
            f"API key: {'Set' if defaults['API_KEY'] else 'Not set'}",
            "Save and return",
        ]
        choice = arrow_menu("MODEL & SERVER SETTINGS", choices)
        if choice is None or choice == 5:
            return

        if choice == 0:
            model = choose_model(defaults["MODEL"])
            if model:
                defaults["MODEL"] = model
                set_env_value("MODEL", model)
        elif choice == 1:
            value = text_setting("Context size", defaults["CTX"])
            if value:
                try:
                    ctx = int(value)
                    if ctx > 0:
                        defaults["CTX"] = str(ctx)
                        set_env_value("CTX", str(ctx))
                except ValueError:
                    print("Context size must be a whole number.")
        elif choice == 2:
            value = text_setting("CPU threads", defaults["THREADS"] or str(physical_threads()))
            if value:
                try:
                    threads = int(value)
                    if threads > 0:
                        defaults["THREADS"] = str(threads)
                        set_env_value("THREADS", str(threads))
                except ValueError:
                    print("Threads must be a whole number.")
        elif choice == 3:
            value = text_setting("Server port", defaults["PORT"])
            if value:
                try:
                    port = int(value)
                    if 1 <= port <= 65535:
                        defaults["PORT"] = str(port)
                        set_env_value("PORT", str(port))
                except ValueError:
                    print("Port must be a whole number.")
        elif choice == 4:
            value = text_setting("API key (leave blank for no key)", "")
            defaults["API_KEY"] = value or ""
            set_env_value("API_KEY", value or "")


def interactive_menu() -> None:
    defaults = env_defaults()
    while True:
        choice = arrow_menu(
            "MODEL SERVER CLI",
            [
                "Setup / update llama.cpp",
                "Run terminal chat",
                "Run local server",
                "Run server with public tunnel",
                "Model & server settings",
                "List available models",
                "Stop server and tunnel",
                "Exit",
            ],
            "Use Up/Down arrows, Enter to run, Esc to exit",
        )
        if choice is None or choice == 7:
            sys.stdout.write("\033[2J\033[H")
            title("GOODBYE")
            return

        if choice == 0:
            run_setup()
        elif choice == 1:
            args = argparse.Namespace(model=None, ctx=None, threads=None)
            chat(args, defaults)
        elif choice == 2:
            args = argparse.Namespace(model=None, ctx=None, threads=None, port=None, api_key=None)
            serve(args, defaults)
        elif choice == 3:
            args = argparse.Namespace(model=None, ctx=None, threads=None, port=None, api_key=None)
            tunnel(args, defaults)
        elif choice == 4:
            configure_menu(defaults)
        elif choice == 5:
            show_models()
            input("\nPress Enter to return to the menu...")
        elif choice == 6:
            stop_all()


def main() -> None:
    if not any(arg for arg in sys.argv[1:]):
        interactive_menu()
        return

    parser = direct_parser()
    args = parser.parse_args()
    defaults = env_defaults()

    if args.command == "setup":
        run_setup(args.update)
    elif args.command == "chat":
        chat(args, defaults)
    elif args.command == "serve":
        serve(args, defaults)
    elif args.command == "tunnel":
        tunnel(args, defaults)
    elif args.command == "stop":
        stop_all()
    elif args.command == "list":
        show_models()
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except RuntimeError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)
