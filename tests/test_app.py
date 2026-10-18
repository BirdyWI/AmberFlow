"""Desktop integration logic with fake hardware; no Tk window, microphone or API."""
from copy import deepcopy
import queue
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from pynput import keyboard
from app import AmberFlowApp, SAMPLE_RATE
from amber_core import DEFAULT_CONFIG


def app_fixture():
    app = AmberFlowApp.__new__(AmberFlowApp)
    app.config = deepcopy(DEFAULT_CONFIG)
    app.events = queue.Queue()
    app.audio_lock = threading.Lock()
    app.frames = []
    app.samples = 0
    app.current_rms = 0.0
    app.canvas = MagicMock()
    app.bars = list(range(5))
    app.recording_end_cue = MagicMock()
    app.max_samples = SAMPLE_RATE * 5
    app.recording = False
    app.busy = False
    app.loading = False
    app.closing = False
    app.stream = None
    app.model = MagicMock()
    app.job_id = 1
    app.cancelled = threading.Event()
    app.pressed = set()
    app.api_key = ""
    app.pending_delivery = None
    app.processing_job = None
    app.hud_hide_timer = None
    app.root = MagicMock()
    app.engine_status = MagicMock()
    app.hide_hud_later = MagicMock()
    app.show_status = MagicMock()
    app.show_result = MagicMock()
    app.feedback = MagicMock()
    app.controller = MagicMock()
    return app


class RecordingTests(unittest.TestCase):
    def test_audio_level_drives_meter(self):
        app = app_fixture()
        app.recording = True
        app.audio_callback(np.full((100, 1), .02), 100, None, False)
        self.assertAlmostEqual(app.current_rms, .36)
        app.update_meter()
        self.assertGreater(app.canvas.coords.call_args_list[2].args[4] - app.canvas.coords.call_args_list[2].args[2], 4)

    def test_control_character_hotkey_is_normalized(self):
        self.assertEqual(AmberFlowApp.key_string(keyboard.KeyCode.from_char("\x01")), "'a'")

    def test_stream_close_failure_does_not_start_processing(self):
        app = app_fixture()
        app.stream = MagicMock()
        app.stream.stop.side_effect = RuntimeError("disconnected")
        stream = app.stream
        app.frames = [np.zeros((SAMPLE_RATE, 1))]
        app.samples = SAMPLE_RATE
        with patch("app.threading.Thread") as worker:
            app.stop_recording()
        worker.assert_not_called()
        stream.close.assert_called_once()
        self.assertFalse(app.busy)

    def test_busy_does_not_open_microphone(self):
        app = app_fixture()
        app.busy = True
        with patch("app.sd.InputStream") as stream:
            app.start_recording("toggle")
        stream.assert_not_called()

    def test_microphone_failure_recoverable(self):
        app = app_fixture()
        with patch("app.foreground_window", return_value=10), patch("app.sd.InputStream", side_effect=RuntimeError):
            app.start_recording("toggle")
        self.assertFalse(app.recording)
        self.assertIsNone(app.stream)
        self.assertEqual(app.frames, [])
        app.show_status.assert_called()

    def test_limit_bounds_audio(self):
        app = app_fixture()
        app.recording = True
        app.max_samples = 10
        app.audio_callback(np.ones((30, 1)), 30, None, False)
        self.assertEqual(app.samples, 10)
        self.assertFalse(app.recording)
        self.assertEqual(app.events.get_nowait(), ("limit", 1))

    def test_stop_transfers_owned_buffer_and_blocks_next_recording(self):
        app = app_fixture()
        app.recording = True
        app.stream = MagicMock()
        old_stream = app.stream
        original = [np.ones((SAMPLE_RATE, 1))]
        app.frames = original
        app.samples = SAMPLE_RATE
        app.target_window = 42
        with patch("app.threading.Thread") as thread:
            app.stop_recording()
        self.assertIs(thread.call_args.kwargs["args"][0], original)
        self.assertIsNot(app.frames, original)
        self.assertEqual(app.frames, [])
        self.assertTrue(app.busy)
        old_stream.close.assert_called_once()
        with patch("app.sd.InputStream") as stream:
            app.start_recording("ptt")
        stream.assert_not_called()

    def test_cancel_closes_microphone_and_discards_frames(self):
        app = app_fixture()
        app.stream = MagicMock()
        stream = app.stream
        app.recording = True
        app.frames = [np.ones((10, 1))]
        app.cancel()
        self.assertTrue(app.cancelled.is_set())
        self.assertEqual(app.frames, [])
        stream.close.assert_called_once()


class DeliveryTests(unittest.TestCase):
    def test_explicit_review_mode_without_clipboard_access(self):
        app = app_fixture()
        with patch("app.pyperclip.copy") as copy:
            app.deliver(1, "private", 10, False, "")
        copy.assert_not_called()
        app.show_result.assert_called_once_with("private", "")

    def test_focus_change_prevents_automatic_paste(self):
        app = app_fixture()
        with patch("app.modifiers_down", return_value=False), patch("app.foreground_window", return_value=20), patch("app.pyperclip.copy") as copy:
            app.deliver(1, "private", 10, True, "")
        copy.assert_called_once_with("private ")
        app.controller.press.assert_not_called()
        app.show_result.assert_not_called()
        self.assertIsNone(app.pending_delivery)

    def test_cancelled_and_stale_jobs_cannot_deliver(self):
        app = app_fixture()
        with patch("app.pyperclip.copy") as copy:
            app.deliver(0, "stale", 10, True, "")
            app.cancelled.set()
            app.deliver(1, "cancelled", 10, True, "")
        copy.assert_not_called()
        app.show_result.assert_not_called()

    def test_held_modifier_waits_then_pastes_without_preview(self):
        app = app_fixture()
        app.pressed = {"Key.shift_r"}
        with patch("app.modifiers_down", return_value=True), patch("app.pyperclip.copy") as copy:
            app.deliver(1, "private", 10, True, "")
        copy.assert_not_called()
        app.show_result.assert_not_called()
        release_callback = app.root.after.call_args.args[1]
        with patch("app.modifiers_down", return_value=False), patch("app.foreground_window", return_value=10), \
             patch("app.pyperclip.copy") as copy, patch("app.pyperclip.paste", return_value="private "), \
             patch("app.paste_shortcut") as paste:
            release_callback()
            app.root.after.call_args.args[1]()
        copy.assert_called_once_with("private ")
        paste.assert_called_once()
        app.show_result.assert_not_called()

    def test_opted_in_same_window_pastes(self):
        app = app_fixture()
        with patch("app.modifiers_down", return_value=False), patch("app.foreground_window", return_value=10), \
             patch("app.pyperclip.copy") as copy, patch("app.pyperclip.paste", return_value="private "), \
             patch("app.paste_shortcut") as paste:
            app.deliver(1, "private", 10, True, "")
            app.root.after.call_args.args[1]()
        copy.assert_called_once_with("private ")
        paste.assert_called_once()

    def test_cancel_while_waiting_prevents_paste(self):
        app = app_fixture()
        with patch("app.modifiers_down", return_value=True):
            app.deliver(1, "private", 10, True, "")
        callback = app.root.after.call_args.args[1]
        app.cancel()
        with patch("app.paste_shortcut") as paste, patch("app.pyperclip.copy") as copy:
            callback()
        paste.assert_not_called()
        copy.assert_not_called()

    def test_unrelated_stale_listener_key_does_not_block_paste(self):
        app = app_fixture()
        app.pressed = {"'a'"}
        with patch("app.modifiers_down", return_value=False), patch("app.foreground_window", return_value=10), \
             patch("app.pyperclip.copy"), patch("app.pyperclip.paste", return_value="private "), \
             patch("app.paste_shortcut") as paste:
            app.deliver(1, "private", 10, True, "")
            app.root.after.call_args.args[1]()
        paste.assert_called_once()

    def test_changed_clipboard_is_not_pasted(self):
        app = app_fixture()
        with patch("app.modifiers_down", return_value=False), patch("app.foreground_window", return_value=10), \
             patch("app.pyperclip.copy"), patch("app.pyperclip.paste", return_value="other"), \
             patch("app.paste_shortcut") as paste:
            app.deliver(1, "private", 10, True, "")
            app.root.after.call_args.args[1]()
        paste.assert_not_called()

    def test_done_keeps_app_busy_until_pending_delivery_finishes(self):
        app = app_fixture()
        app.processing_job = 1
        app.pending_delivery = (1, "private", 10, "")
        app.events.put(("done", 1))
        app.poll()
        self.assertTrue(app.busy)
        self.assertIsNone(app.processing_job)
        app.finish_delivery("ok")
        self.assertFalse(app.busy)


class TranscriptionTests(unittest.TestCase):
    def test_cancellation_during_segments_does_not_polish_or_deliver(self):
        app = app_fixture()
        def segments():
            app.cancelled.set()
            yield SimpleNamespace(text="private")
        app.model.transcribe.return_value = (segments(), None)
        with patch("app.polish_text") as polish:
            app.transcribe([np.zeros((100, 1))], app.config, app.model, 1, app.cancelled, 10, "")
        polish.assert_not_called()
        self.assertEqual(app.events.get_nowait(), ("done", 1))

    def test_cancellation_before_work_skips_model_and_cloud(self):
        app = app_fixture()
        app.cancelled.set()
        frames = [np.zeros((100, 1))]
        with patch("app.polish_text") as polish:
            app.transcribe(frames, app.config, app.model, 1, app.cancelled, 10, "")
        app.model.transcribe.assert_not_called()
        polish.assert_not_called()
        self.assertEqual(frames, [])
        self.assertEqual(app.events.get_nowait(), ("done", 1))

    def test_polish_failure_retains_direct_insertion_preference(self):
        app = app_fixture()
        app.config["auto_paste"] = True
        app.model.transcribe.return_value = ([MagicMock(text="Original")], None)
        with patch("app.polish_text", side_effect=RuntimeError("secret")), patch("builtins.print") as log:
            app.transcribe([np.zeros((100, 1))], app.config, app.model, 1, app.cancelled, 10, "")
        event, payload = app.events.get_nowait()
        self.assertEqual(event, "result")
        self.assertEqual(payload[1], "Original")
        self.assertTrue(payload[3])
        log.assert_not_called()


class ModelTests(unittest.TestCase):
    def test_gpu_failure_falls_back_to_cpu(self):
        app = app_fixture()
        app.config["compute_device"] = "cuda"
        model = MagicMock()
        model.transcribe.return_value = ([], None)
        with patch("app.WhisperModel", side_effect=[RuntimeError("missing DLL"), model]) as factory, \
             patch("app.threading.Thread", side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            app.load_model()
        self.assertEqual(factory.call_args.kwargs["device"], "cpu")
        event, payload = app.events.get_nowait()
        self.assertEqual(event, "model")
        self.assertIn("Fallback", payload[1])

    def test_both_model_attempts_fail_recoverably(self):
        app = app_fixture()
        app.config["compute_device"] = "cuda"
        with patch("app.WhisperModel", side_effect=RuntimeError("no model")), \
             patch("app.threading.Thread", side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            app.load_model()
        self.assertEqual(app.events.get_nowait(), ("model_error", None))

    def test_model_failure_signals_error_and_completion(self):
        app = app_fixture()
        app.model.transcribe.side_effect = RuntimeError("sensitive detail")
        with patch("builtins.print") as log:
            app.transcribe([np.zeros((100, 1))], app.config, app.model, 1, app.cancelled, 10, "")
        self.assertEqual(app.events.get_nowait(), ("job_error", 1))
        self.assertEqual(app.events.get_nowait(), ("done", 1))
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
