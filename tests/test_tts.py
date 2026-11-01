"""3.1: read aloud — the settings store, the selection cleanup, and
SpeechReader against Qt's mock engine (offscreen, no audio).
"""

import tempfile
import unittest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lekhak import tts  # noqa: E402

_application = QApplication.instance() or QApplication([])
_application.setOrganizationName("Lekhak")
_application.setApplicationName("Lekhak")
_settings_dir = tempfile.mkdtemp(prefix="lekhak-tts-settings-")
QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, _settings_dir)


class SpeechTextTests(unittest.TestCase):
    def test_paragraph_separators_become_newlines(self):
        self.assertEqual(tts.speech_text("one two three"),
                         "one\ntwo\nthree")

    def test_plain_text_is_untouched(self):
        self.assertEqual(tts.speech_text("just words"), "just words")


class TTSSettingsTests(unittest.TestCase):
    def test_round_trip(self):
        tts.save_settings(tts.TTSSettings(voice="Anne", rate=0.35,
                                          engine="mock"))

        loaded = tts.load_settings()

        self.assertEqual(loaded.voice, "Anne")
        self.assertEqual(loaded.rate, 0.35)
        self.assertEqual(loaded.engine, "mock")

    def test_defaults_when_empty(self):
        tts.save_settings(tts.TTSSettings())

        loaded = tts.load_settings()

        self.assertEqual(loaded.voice, "")
        self.assertEqual(loaded.rate, 0.0)
        self.assertEqual(loaded.engine, tts.DEFAULT_ENGINE)


class SpeechReaderTests(unittest.TestCase):
    """The mock engine stands in for speechd: same API, no audio."""

    def setUp(self):
        self.reader = tts.SpeechReader(engine_name="mock")

    def test_engine_connects_and_lists_voices(self):
        self.assertTrue(self.reader.ensure_engine())

        names = self.reader.voice_names()

        self.assertIn("Bob", names)
        self.assertIn("Anne", names)

    def test_speak_and_stop_are_safe(self):
        self.reader.speak("Hello there.")
        self.reader.stop()

        self.assertIsNotNone(self.reader.state())

    def test_blank_text_is_not_spoken(self):
        self.reader.speak("   \n  ")

        # The engine never started; mock stays Ready or untouched.
        state = self.reader.state()
        self.assertTrue(state is None or state.name in ("Ready", "Idle"))

    def test_apply_settings_with_empty_store(self):
        tts.save_settings(tts.TTSSettings(engine="mock"))

        self.reader.apply_settings()

        self.assertIsNotNone(self.reader.state())

    def test_voice_name_reads_property_or_method(self):
        class PropertyVoice:
            name = "Pat"

        class MethodVoice:
            def name(self):
                return "Mel"

        self.assertEqual(tts.voice_name(PropertyVoice()), "Pat")
        self.assertEqual(tts.voice_name(MethodVoice()), "Mel")


if __name__ == "__main__":
    unittest.main()
