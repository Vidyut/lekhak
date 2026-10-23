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

# The shipped proofreading prompt (docs/AI.md: "bloopers, not prose").
# Minimal edits is the whole contract with a small model — left to its
# own judgement a small model smooths voice and tidies deliberate
# fragments, so the prompt forbids exactly that.
PROOFREAD_SYSTEM = (
    "You are a copy editor for fiction. Fix only bloopers: typos, "
    "spelling, grammar, doubled words or lines, stray spaces and "
    "punctuation. Make the minimal edit that repairs each blooper and "
    "nothing more — do not polish, rephrase, smooth the author's voice "
    "or restructure sentences; the wording and paragraphing are "
    "deliberate. Return only the corrected text, with no commentary "
    "and no quotation marks around it."
)

# What both AI menu items show when no model is configured: not a shrug
# but the shortest path to a working setup (BUILD-NOW 8 — the menu
# explains instead of failing silently).
NO_MODEL_MESSAGE = (
    "No AI model is configured yet.\n\n"
    "Local model — nothing leaves your computer:\n"
    "  1. Install Ollama from https://ollama.com\n"
    "  2. In a terminal:  ollama pull qwen2.5:7b   (any small model)\n"
    "  3. Preferences → Model: qwen2.5:7b — the endpoint "
    "http://localhost:11434/v1 is already the default.\n\n"
    "Small models are error-prone: proofread bloopers with them, not "
    "prose, and nothing unsupervised."
)


class AIError(Exception):
    """Any refusal or transport failure, with a message meant for the
    status bar / a warning box."""


@dataclass(frozen=True)
class AISettings:
    endpoint: str = DEFAULT_ENDPOINT
    model: str = ""
    key: str = ""
    # Empty means "use PROOFREAD_SYSTEM"; a stored copy is a writer who
    # tuned the wording (docs/PREFERENCES.md, AI category, behind the
    # accordion with the do-not-edit-unless-you-know warning).
    prompt: str = ""


def load_settings() -> AISettings:
    settings = QSettings()
    return AISettings(
        endpoint=str(settings.value("ai/endpoint", DEFAULT_ENDPOINT)),
        model=str(settings.value("ai/model", "")),
        key=str(settings.value("ai/key", "")),
        prompt=str(settings.value("ai/prompt", "")),
    )


def save_settings(settings: AISettings) -> None:
    store = QSettings()
    store.setValue("ai/endpoint", settings.endpoint or DEFAULT_ENDPOINT)
    store.setValue("ai/model", settings.model)
    store.setValue("ai/key", settings.key)
    store.setValue("ai/prompt", settings.prompt)


def proofread_system(settings: AISettings | None = None) -> str:
    """The system prompt proofreading actually sends."""
    prompt = (settings or load_settings()).prompt.strip()
    return prompt or PROOFREAD_SYSTEM


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
        raise AIError(NO_MODEL_MESSAGE)
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
    text = content.strip()
    if not text:
        # A thinking model that hits its token cap mid-reasoning answers
        # in the reasoning field with no content at all (seen against a
        # live Ollama with qwen3.5:2b) — "nothing" is not an explanation.
        message = body["choices"][0]["message"]
        reasoning = message.get("reasoning") or message.get(
            "reasoning_content") or ""
        if str(reasoning).strip():
            raise AIError(
                f"Model {settings.model} returned no usable answer: it "
                "spent the whole reply thinking and ran into its token "
                "limit. Use a small non-thinking model instead "
                "(ollama pull phi4-mini)."
            )
    return text
