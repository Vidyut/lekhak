"""Read prose aloud (3.1).

Thin wrapper over Qt's QTextToSpeech: pick an engine (speechd when the
system has it — speech-dispatcher and espeak-ng are installed here —
else whatever engine exists), list its voices, speak plain text.
Preferences hold the chosen voice, rate and engine; the Speak menu
holds read-aloud, pause and stop. Nothing here synthesizes audio
itself; the backend does, and the mock engine covers tests.
"""

from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtTextToSpeech import QTextToSpeech

DEFAULT_ENGINE = "speechd"


@dataclass(frozen=True)
class TTSSettings:
    voice: str = ""
    rate: float = 0.0     # QTextToSpeech rates run -1.0 .. 1.0
    engine: str = DEFAULT_ENGINE


def load_settings() -> TTSSettings:
    settings = QSettings()
    try:
        rate = float(settings.value("tts/rate", 0.0))
    except (TypeError, ValueError):
        rate = 0.0
    return TTSSettings(
        voice=str(settings.value("tts/voice", "")),
        rate=rate,
        engine=(str(settings.value("tts/engine", DEFAULT_ENGINE))
                or DEFAULT_ENGINE),
    )


def save_settings(settings: TTSSettings) -> None:
    store = QSettings()
    store.setValue("tts/voice", settings.voice)
    store.setValue("tts/rate", settings.rate)
    store.setValue("tts/engine", settings.engine or DEFAULT_ENGINE)


def speech_text(selected: str) -> str:
    """Selection text fit for speaking.

    QTextCursor.selectedText() joins paragraphs with Unicode
    separators the engines read as glued words; a newline becomes a
    pause instead.
    """
    return selected.replace("\u2029", "\n").replace("\u2028", "\n")


def voice_name(voice) -> str:
    """QVoice.name is a method in some PySide6 builds and a plain
    property in others; ask whichever this one is."""
    name = voice.name
    return str(name() if callable(name) else name)


class SpeechReader(QObject):
    """Owns the QTextToSpeech engine for one window.

    Constructed lazily on the first read-aloud: opening a
    speech-dispatcher connection costs real time and most sessions
    never read aloud. ``state_changed`` forwards the engine state so
    the UI can tell speaking from idle.
    """
    state_changed = Signal(object)

    def __init__(self, parent=None, engine_name: str | None = None) -> None:
        super().__init__(parent)
        self._engine_name = engine_name
        self._engine: QTextToSpeech | None = None
        self._voices: list = []

    def ensure_engine(self) -> bool:
        """Connect the engine; False when this system has none."""
        if self._engine is not None:
            return True
        engines = QTextToSpeech.availableEngines()
        wanted = self._engine_name or load_settings().engine
        name = wanted if wanted in engines else (
            engines[0] if engines else None)
        if name is None:
            return False
        self._engine = QTextToSpeech(name)
        self._engine.stateChanged.connect(self._forward_state)
        self._voices = list(self._engine.availableVoices())
        return True

    def _forward_state(self, state) -> None:
        # A direct signal-to-signal connect is refused across the
        # C++/PyObject boundary; re-emit by hand.
        self.state_changed.emit(state)

    def voice_names(self) -> list[str]:
        if not self.ensure_engine():
            return []
        return [voice_name(voice) for voice in self._voices]

    def apply_settings(self) -> None:
        """Put the saved voice and rate on the engine."""
        if not self.ensure_engine() or self._engine is None:
            return
        saved = load_settings()
        for voice in self._voices:
            if voice_name(voice) == saved.voice:
                self._engine.setVoice(voice)
                break
        self._engine.setRate(saved.rate)

    def speak(self, text: str) -> None:
        if not text.strip() or not self.ensure_engine():
            return
        self.apply_settings()
        self._engine.say(text)

    def pause(self) -> None:
        if self._engine is not None:
            self._engine.pause()

    def resume(self) -> None:
        if self._engine is not None:
            self._engine.resume()

    def stop(self) -> None:
        if self._engine is not None:
            self._engine.stop()

    def state(self):
        return self._engine.state() if self._engine is not None else None
