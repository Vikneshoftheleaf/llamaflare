# model-server

A Linux-first interactive CLI for running local GGUF models with
[llama.cpp](https://github.com/ggml-org/llama.cpp), chatting through its
OpenAI-compatible API, and optionally making that API reachable through a
Cloudflare Tunnel.

Use the arrow keys to navigate the menu. The first run offers the default
Qwen2.5 0.5B Instruct GGUF model; additional GGUF files can be downloaded from
Hugging Face and are kept under this repository's `models/` directory.

## Requirements

- Linux and Python 3.10+
- Git
- `llama-server` from llama.cpp on `PATH`
- `cloudflared` on `PATH` for tunnel support

llama.cpp uses a compatible GPU backend when available. Build it with the
backend appropriate for your hardware; a CPU build also works.

## Install

From the cloned repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
model-server
```

For example, to build llama.cpp with NVIDIA CUDA support, install the CUDA
toolkit and CMake, then follow the upstream llama.cpp build instructions:

```bash
git clone https://github.com/ggml-org/llama.cpp.git
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON
cmake --build llama.cpp/build --config Release -j
```

Add `llama.cpp/build/bin` to `PATH` (or install `llama-server` into a
directory already on `PATH`). For CPU-only builds, omit `-DGGML_CUDA=ON`.
Install `cloudflared` using Cloudflare's instructions for your Linux
distribution if you want to use tunnels.

## Use

- **Chat with the local model** streams replies and keeps conversation context
  for the current chat. Enter `/clear` to reset it or `/exit` to leave chat.
- **Select or download models** selects a downloaded GGUF or fetches one by
  Hugging Face repository ID and exact GGUF filename.
- **Set up local server** starts `llama-server` on `127.0.0.1:8080` and a
  local authenticated proxy on `127.0.0.1:8081`. The model server uses GPU
  offload when supported by the installed llama.cpp build.
- **Set up Cloudflare Tunnel** saves a named-tunnel token locally, starts
  `cloudflared`, and displays the API bearer token for configuring clients.
- **Look for Git updates** fetches the configured upstream and offers a
  fast-forward only when the working tree is safe to update.

The Cloudflare dashboard must have a public hostname whose service points to
`http://127.0.0.1:8081`. Do not point the public hostname at port 8080: that is
the local model server, while the proxy enforces bearer-token authentication.
Use the API token shown in the Tunnel menu with clients, for example:

```bash
curl http://YOUR_PUBLIC_HOSTNAME/v1/models \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

The tunnel token and API key are saved outside the checkout under
`~/.config/model-server/` with owner-only permissions. Runtime logs and PID
files are under `~/.local/state/model-server/`. Downloaded weights stay in
`models/` but are intentionally excluded from Git.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```
