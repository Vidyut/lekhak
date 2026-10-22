"""Local-LLM client (2.4, layer 2).

Talks to any OpenAI-compatible ``/chat/completions`` endpoint with
nothing but urllib — Ollama's localhost server is the default, but an
endpoint/key/model triple in Preferences covers LM Studio, llama.cpp
server and the rest. Responses land in the editor only through the
tracked-changes path (apply_tracked_replacement), so a model can never
rewrite the manuscript behind the writer's back.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from PySide6.QtCore import QSettings

DEFAULT_ENDPOINT = "http://localhost:11434/v1"


class AIError(Exception):
    """Any refusal or transport failure, with a message meant for the
    status bar / a warning box."""


@dataclass(frozen=True)
class AISettings:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = ""
    key: str = ""


def load_settings() -> AISettings:
    settings = QSettings()
    return AISettings(
        endpoint=str(settings.value("ai/endpoint", DEFAULT_ENDPOINT)),
        model=str(settings.value("ai/model", "")),
        key=str(settings.value("ai/key", "")),
    )


def save_settings(settings: AISettings) -> None:
    store = QSettings()
    store.setValue("ai/endpoint", settings.endpoint or DEFAULT_ENDPOINT)
    store.setValue("ai/model", settings.model)
    store.setValue("ai/key", settings.key)


def _sends_key_in_the_clear(endpoint: str) -> bool:
    """True for a non-local endpoint reached over plain http.

    Local endpoints are fine — Ollama's own default is
    http://localhost:11434/v1 — and so is a remote https one. What must
    never happen is a bearer key (and with it the manuscript text) going
    out over an unencrypted network connection.
    """
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme != "http":
        return False
    return (parsed.hostname or "") not in {"localhost", "127.0.0.1", "::1"}


def complete(system: str, user: str,
             settings: AISettings | None = None) -> str:
    """One chat round-trip; returns the assistant message text.

    No streaming (a skeleton does not need it), no retries — a failure
    comes back as AIError and the caller decides what to tell the writer.
    """
    settings = settings or load_settings()
    if not settings.model.strip():
        raise AIError(
            "No AI model set — fill in model and endpoint in Preferences.")
    if settings.key and _sends_key_in_the_clear(settings.endpoint):
        raise AIError(
            "Refusing to send the API key unencrypted: "
            f"{settings.endpoint} is plain http and not localhost. Use an "
            "https:// endpoint, or keep the key off a remote http one."
        )
    endpoint = settings.endpoint.rstrip("/")
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    request = urllib.request.Request(
        endpoint + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if settings.key:
        request.add_header("Authorization", "Bearer " + settings.key)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", "replace")[:300]
        except OSError:
            pass
        raise AIError(
            f"AI endpoint returned HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, OSError) as error:
        raise AIError(
            f"Cannot reach the AI endpoint at {endpoint}: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise AIError(f"AI endpoint returned invalid JSON: {error}") from error
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise AIError(
            "AI endpoint response has no assistant message") from error
    if not isinstance(content, str):
        raise AIError("AI endpoint response message is not text")
    return content.strip()
