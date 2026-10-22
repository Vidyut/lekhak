"""Deterministic typo underlining: a dictionary pass, no model (8).

aspell first, hunspell as fallback, both in batch mode — the whole
document is checked in one process spawn per refresh, and a session
word cache keeps repeat words free, so ordinary prose costs one process
at most. Unlike pdf's per-export converter probe, the engine probe runs
once per process: squiggles refresh every half second while typing.

Ranges come back as UTF-16 code-unit offsets, because that is what a
QTextDocument cursor position is; a code-point index would drift by one
per emoji past it.

Failure means "flag nothing", never "flag everything": a checker that
is missing, crashing or timing out leaves the manuscript clean rather
than buried in false positives.
"""

from __future__ import annotations

import re
import shutil
import subprocess

# Word runs as a writer means them: letters (accented included),
# optionally joined by one apostrophe — "don't", "don’t", "Aaxyl's".
# Digits excluded: "2nd" is not a typo the dictionary can judge.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)

ENGINES = (("aspell", ["list"]), ("hunspell", ["-l"]))
BATCH_TIMEOUT = 15
PROBE_TIMEOUT = 5

_engine: list[str] | None = None
_probed = False
_session_cache: dict[str, bool] = {}


def reset() -> None:
    """Forget the probe and the word cache (tests, and a re-install)."""
    global _engine, _probed
    _probed = False
    _engine = None
    _session_cache.clear()


def find_engine() -> list[str] | None:
    """The first spell checker on PATH that runs, probed once.

    Once per process, not per keystroke: a dead or absent checker
    answers None every time and the toggle can say so up front.
    """
    global _engine, _probed
    if _probed:
        return _engine
    _probed = True
    for name, args in ENGINES:
        path = shutil.which(name)
        if not path:
            continue
        try:
            result = subprocess.run(
                [path, *args], input="", capture_output=True,
                text=True, timeout=PROBE_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            _engine = [path, *args]
            return _engine
    _engine = None
    return None


def _unknown(engine: list[str], words: list[str]) -> set[str] | None:
    """Batch-check every unseen word in one spawn.

    None means the checker failed and nothing may be concluded — the
    caller flags nothing and, deliberately, caches nothing either, so
    the next refresh retries instead of trusting a broken reading.
    """
    try:
        result = subprocess.run(
            engine, input="\n".join(words),
            capture_output=True, text=True, timeout=BATCH_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return {line.strip()
            for line in result.stdout.splitlines() if line.strip()}


def misspellings(
    text: str,
    cache: dict[str, bool] | None = None,
) -> list[tuple[int, int]]:
    """(start, end) UTF-16 ranges of words the dictionary rejects.

    The cache maps exact words to verdicts for the session; words in it
    are never sent to the checker again, so a re-read of an unchanged
    document costs no processes at all.
    """
    engine = find_engine()
    if engine is None or not text:
        return []
    if cache is None:
        cache = _session_cache
    matches = list(_WORD_RE.finditer(text))
    if not matches:
        return []
    unseen: list[str] = []
    seen: set[str] = set()
    for match in matches:
        word = match.group(0)
        if word not in seen and word not in cache:
            seen.add(word)
            unseen.append(word)
    if unseen:
        unknown = _unknown(engine, unseen)
        if unknown is None:
            return []
        for word in unseen:
            cache[word] = word in unknown
    return [
        (_utf16(text, match.start()), _utf16(text, match.end()))
        for match in matches
        # True = the checker rejected it, and only those are squiggled.
        if cache.get(match.group(0), False)
    ]


def _utf16(text: str, index: int) -> int:
    """Code-point index → QTextDocument offset (UTF-16 code units)."""
    return len(text[:index].encode("utf-16-le")) // 2
