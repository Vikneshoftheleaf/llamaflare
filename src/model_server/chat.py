from __future__ import annotations

import json
import sys
from typing import Callable

import httpx


def chat_loop(base_url: str, api_key: str = "") -> None:
    messages: list[dict[str, str]] = []
    print("Chat started. Enter /clear to reset the conversation or /exit to return.")
    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_text:
            continue
        if user_text == "/exit":
            return
        if user_text == "/clear":
            messages.clear()
            print("Conversation cleared.")
            continue

        messages.append({"role": "user", "content": user_text})
        payload = {"model": "local-model", "messages": messages, "stream": True}
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        assistant_text: list[str] = []
        try:
            with httpx.stream(
                "POST",
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=180.0,
            ) as response:
                response.raise_for_status()
                print("Assistant: ", end="", flush=True)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    content = line[5:].strip()
                    if content == "[DONE]":
                        break
                    try:
                        chunk = json.loads(content)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    token = choices[0].get("delta", {}).get("content", "")
                    if token:
                        assistant_text.append(token)
                        print(token, end="", flush=True)
                print()
        except httpx.HTTPError as exc:
            messages.pop()
            print(f"\nChat request failed: {exc}", file=sys.stderr)
            continue
        except (KeyError, TypeError, ValueError) as exc:
            messages.pop()
            print(f"\nUnexpected response from the model server: {exc}", file=sys.stderr)
            continue
        messages.append({"role": "assistant", "content": "".join(assistant_text)})
