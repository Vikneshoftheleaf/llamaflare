# Server for Models with Tunnel

Run a small LLM on a low-RAM, CPU-only Windows, Linux, or macOS PC with [llama.cpp](https://github.com/ggml-org/llama.cpp):
terminal chat, a local API + web UI, or a public API through a Cloudflare quick tunnel (with an API key).

Re-running is safe: the build, cloudflared and the model are only fetched when missing.

## Interactive CLI (Windows, Linux, and macOS)

Run the CLI with no command. It opens a titled terminal menu with arrow-key selection:

**Windows (Command Prompt or PowerShell):**
```bat
.\run.bat
```

Or use the PowerShell-native launcher:
```powershell
.\run.ps1
```

**Linux / macOS:**
```bash
./run.sh
```

The menu can run setup, start terminal chat, start a local server, start a public tunnel, list models, stop services, or exit.
Use **Up/Down** to select, **Enter** to run, and **Esc** to go back or exit.

The **Model & server settings** screen lets you choose a model and change context size, threads, port, and API key. Settings are saved to `.env`.

## Quick start

**Linux / macOS**
```bash
git clone https://github.com/<your-username>/tiny-llamacpp-tunnel.git
cd tiny-llamacpp-tunnel
./setup.sh
./run.sh
```

**Windows**
```bat
git clone https://github.com/<your-username>/tiny-llamacpp-tunnel.git
cd tiny-llamacpp-tunnel
powershell -ExecutionPolicy Bypass -File setup.ps1
.\run.bat
```

## Usage

```bash
./run.sh                         # interactive titled menu
./run.sh chat                    # CLI chat with the default model
./run.sh chat -m qwen2.5-1.5b   # another model from models.conf
./run.sh serve                   # local API + web UI
./run.sh tunnel                  # public URL + API key
./run.sh chat -m ~/my-model.gguf
./run.sh chat -m https://.../x.gguf
./run.sh list                    # models in models.conf
./run.sh stop                    # stop server and tunnel
./setup.sh --update                # update and rebuild llama.cpp
```

Defaults live in `.env`. Add models by appending a `key|filename|url` line to `models.conf`.

## Calling the API

The server is OpenAI-compatible:

```bash
curl https://<your-url>.trycloudflare.com/v1/chat/completions \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}'
```

## Low-RAM tips

- Lower `--ctx` (1024 to 2048) to reduce memory use.
- Use a 0.5B to 2B model on 4 GB machines. 3B is tight.
- Building llama.cpp is the heaviest step. `JOBS=1 ./setup.sh` is slower but uses less RAM. Zram or a swap file helps too.
- Stay in terminal mode (no desktop) to keep RAM free.

## Security

The quick tunnel URL is public and changes each time. The API key stops others from using the API, but treat the URL and key as secrets, and run `./run.sh --stop` when finished. Never commit `.env`.
For a permanent setup use a Cloudflare named tunnel, ideally with Cloudflare Access.

## Troubleshooting

- Windows: run `powershell -ExecutionPolicy Bypass -File setup.ps1` to install or detect Git, CMake, Python, and llama.cpp. Use `.\run.bat` or `.\run.ps1`.
- PowerShell says `run.bat` is not recognized: use `.\run.bat`.
- Python is not found: install Python 3 with `winget install --id Python.Python.3.12 -e`, reopen the terminal, then run `.\run.bat`.
- Download 404: the URL in `models.conf` may have changed. Check the model's page on Hugging Face and update the line.
- Server won't start: see `.state/server.log`. Tunnel issues: `.state/tunnel.log`.
- Very slow: check your CPU with `lscpu`; fewer threads or a smaller model can help.
