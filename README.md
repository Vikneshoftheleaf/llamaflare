# Server for Models with Tunnel

Run a small LLM on a low-RAM, CPU-only Linux PC with [llama.cpp](https://github.com/ggml-org/llama.cpp):
terminal chat, a local API + web UI, or a public API through a Cloudflare quick tunnel (with an API key).

Re-running is safe: the build, cloudflared and the model are only fetched when missing.

## Quick start

```bash
git clone https://github.com/<your-username>/tiny-llamacpp-tunnel.git
cd tiny-llamacpp-tunnel
./setup.sh          # once: builds llama.cpp for your CPU, installs cloudflared
./run.sh            # terminal chat (downloads the model on first run)
```

## Usage

```bash
./run.sh                           # CLI chat with the default model
./run.sh -m qwen2.5-1.5b           # another model from models.conf
./run.sh --serve                   # local API + web UI on http://127.0.0.1:8080
./run.sh --tunnel                  # public URL + API key
./run.sh -m gemma2-2b --ctx 1024 --tunnel
./run.sh -m ~/my-model.gguf        # your own file
./run.sh -m https://.../x.gguf     # or a direct download URL
./run.sh --list                    # models in models.conf
./run.sh --stop                    # stop server and tunnel
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

- Download 404: the URL in `models.conf` may have changed. Check the model's page on Hugging Face and update the line.
- Server won't start: see `.state/server.log`. Tunnel issues: `.state/tunnel.log`.
- Very slow: check your CPU with `lscpu`; fewer threads or a smaller model can help.
