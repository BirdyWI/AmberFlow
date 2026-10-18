from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from amber_core import (ConfigError, ConfigStore, DEFAULT_CONFIG, NoRedirect,
                        canonical_hotkey, clean_text, polish_text, validate_config, validate_url)


class ConfigTests(unittest.TestCase):
    def test_direct_paste_is_default_but_review_choice_is_preserved(self):
        self.assertTrue(validate_config({})["auto_paste"])
        self.assertFalse(validate_config({"auto_paste": False})["auto_paste"])

    def test_defaults_are_independent(self):
        first = validate_config({})
        first["hotkeys"]["ptt"] = "Key.f2"
        self.assertEqual(validate_config({})["hotkeys"]["ptt"], DEFAULT_CONFIG["hotkeys"]["ptt"])

    def test_invalid_shapes(self):
        for value in (None, [], "config", {"hotkeys": None}, {"llm_polish": []},
                      {"replacements": {"": "oops"}}, {"sound_feedback": 1},
                      {"max_recording_seconds": True}, {"max_recording_seconds": 601},
                      {"input_device": -1}, {"prompt_terms": [23]}, {"model_size": "../private"}):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_config(value)

    def test_duplicate_hotkeys_rejected(self):
        with self.assertRaises(ConfigError):
            validate_config({"hotkeys": {"ptt": "Key.esc"}})

    def test_hotkeys_normalized(self):
        self.assertEqual(canonical_hotkey("Key.shift_r + Key.ctrl_r"), "Key.ctrl_r + Key.shift_r")

    def test_sensitive_and_obsolete_keys_removed(self):
        data = validate_config({"llm_polish": {"cloud_key": "test-secret"}, "device": "cuda"})
        self.assertNotIn("test-secret", json.dumps(data))
        self.assertNotIn("device", data)

    def test_missing_config_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing" / "config.json"
            data, warning = ConfigStore(path).load()
            self.assertFalse(path.parent.exists())
            self.assertEqual(data, DEFAULT_CONFIG)

    def test_corrupt_config_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ConfigError):
                ConfigStore(path).load()
            self.assertEqual(path.read_text(), "{broken")

    def test_atomic_save_strips_key_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp) / "config.json")
            data = deepcopy(DEFAULT_CONFIG)
            data["llm_polish"]["cloud_key"] = "test-secret"
            store.save(data)
            self.assertNotIn("test-secret", store.path.read_text())
            self.assertEqual(store.load()[0], DEFAULT_CONFIG)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_failed_replace_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ConfigStore(Path(tmp) / "config.json")
            store.save(DEFAULT_CONFIG)
            before = store.path.read_bytes()
            with patch("amber_core.os.replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    store.save({"language": "en"})
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_legacy_import_keeps_source_and_disables_cloud(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "dictionary.json"
            legacy.write_text(json.dumps({"llm_polish": {"mode": "cloud", "cloud_key": "test-secret"},
                                          "model_size": "large-v3-turbo", "auto_paste": True}))
            before = legacy.read_bytes()
            new = Path(tmp) / "new.json"
            data, warning = ConfigStore(new).load(legacy)
            self.assertEqual(data["model_size"], "large-v3-turbo")
            self.assertEqual(data["llm_polish"]["mode"], "off")
            self.assertTrue(data["auto_paste"])
            self.assertNotIn("test-secret", json.dumps(data))
            self.assertIn("Klartext", warning)
            self.assertFalse(new.exists())
            self.assertEqual(legacy.read_bytes(), before)


class TextTests(unittest.TestCase):
    def test_backslash_is_literal(self):
        config = validate_config({"replacements": {"Pfad": r"C:\Users\Test\1"}})
        self.assertEqual(clean_text("Pfad", config), r"C:\Users\Test\1")

    def test_paragraphs_preserved(self):
        self.assertEqual(clean_text("eins\n\nzwei", DEFAULT_CONFIG), "eins\n\nzwei")

    def test_filler_does_not_eat_newline(self):
        self.assertEqual(clean_text("eins ähm\nzwei", DEFAULT_CONFIG), "eins \nzwei")

    def test_voice_paragraph(self):
        self.assertEqual(clean_text("eins neuer Absatz zwei", DEFAULT_CONFIG), "eins\n\nzwei")

    def test_disabled_cleanup(self):
        config = validate_config({"smart_cleanup": False})
        self.assertEqual(clean_text("ähm  Test", config), "ähm  Test")


class NetworkTests(unittest.TestCase):
    def test_cloud_requires_https(self):
        for url in ("http://example.com/api", "file:///tmp/a", "https://user:secret@example.com/api",
                    "https://example.com:bad", "https://example.com/a?key=secret", "https://example.com/#key"):
            with self.subTest(url=url), self.assertRaises(ConfigError):
                validate_url(url)

    def test_local_endpoint_cannot_be_remote(self):
        for url in ("http://example.com/api", "http://localhost.example.com", "http://192.168.1.5/api"):
            with self.subTest(url=url), self.assertRaises(ConfigError):
                validate_url(url, local=True)
        for host in ("localhost", "127.0.0.1", "[::1]"):
            self.assertEqual(validate_url(f"http://{host}:11434/api", local=True), f"http://{host}:11434/api")

    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    def test_off_and_cancelled_never_request(self):
        with patch("amber_core.urllib.request.build_opener") as build:
            self.assertEqual(polish_text("private", DEFAULT_CONFIG), "private")
            stop = threading.Event()
            stop.set()
            config = validate_config({"llm_polish": {"mode": "cloud"}})
            self.assertEqual(polish_text("private", config, "secret", stop), "private")
            build.assert_not_called()

    def test_missing_key_never_requests(self):
        with patch("amber_core.urllib.request.build_opener") as build, self.assertRaises(ConfigError):
            polish_text("private", validate_config({"llm_polish": {"mode": "cloud"}}))
        build.assert_not_called()

    def test_payload_and_response(self):
        config = validate_config({"llm_polish": {"mode": "cloud"}})
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"choices":[{"message":{"content":" cleaned "}}]}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch("amber_core.urllib.request.build_opener", return_value=opener):
            self.assertEqual(polish_text("original", config, "test-secret"), "cleaned")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
        self.assertEqual(json.loads(request.data)["messages"][1]["content"], "original")
        self.assertNotIn("test-secret", request.full_url)

    def test_oversized_response_rejected(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"x" * 1_048_577
        opener = MagicMock()
        opener.open.return_value = response
        with patch("amber_core.urllib.request.build_opener", return_value=opener), self.assertRaises(ValueError):
            polish_text("text", validate_config({"llm_polish": {"mode": "ollama"}}))


if __name__ == "__main__":
    unittest.main()
