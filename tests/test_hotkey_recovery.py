import unittest
from unittest.mock import MagicMock, patch
from pynput import keyboard
from test_app import app_fixture


class HotkeyRecoveryTests(unittest.TestCase):
    def make_app(self):
        app = app_fixture()
        app.capture = None
        app.settings = None
        app.status = MagicMock()
        app.start_recording = MagicMock()
        app.stop_recording = MagicMock()
        app.listener = MagicMock()
        app.listener.is_alive.return_value = True
        app.last_listener_restart = 0
        app.start_listener = MagicMock()
        return app

    def state(self, down):
        def read(name):
            key = keyboard.Key[name[4:]] if name.startswith('Key.') else keyboard.KeyCode.from_char(name[1:-1])
            return key, name in down
        return read

    def test_silent_hook_loss_f8_works_without_listener_events(self):
        app = self.make_app()
        with patch.object(app, 'physical_key', side_effect=self.state({'Key.f8'})):
            app.reconcile_hotkeys()
            app.reconcile_hotkeys()
        app.start_recording.assert_called_once_with('toggle')
        app.start_listener.assert_called_once()
        with patch.object(app, 'physical_key', side_effect=self.state(set())):
            app.reconcile_hotkeys()
        with patch.object(app, 'physical_key', side_effect=self.state({'Key.f8'})):
            app.reconcile_hotkeys()
        self.assertEqual(app.start_recording.call_count, 2)

    def test_missing_release_clears_stale_key_and_stops_ptt(self):
        app = self.make_app()
        app.pressed = {'Key.ctrl_r', 'Key.shift_r', "'x'"}
        app.recording = True
        app.mode = 'ptt'
        with patch.object(app, 'physical_key', side_effect=self.state({'Key.ctrl_r'})):
            app.reconcile_hotkeys()
        self.assertEqual(app.pressed, {'Key.ctrl_r'})
        app.stop_recording.assert_called_once()

    def test_normal_hook_press_is_not_duplicated_by_fallback(self):
        app = self.make_app()
        app.handle_key(True, keyboard.Key.f8)
        with patch.object(app, 'physical_key', side_effect=self.state({'Key.f8'})):
            app.reconcile_hotkeys()
        app.start_recording.assert_called_once()
        app.start_listener.assert_not_called()

    def test_settings_suppress_recording_and_capture_is_not_disturbed(self):
        app = self.make_app()
        app.settings = object()
        with patch.object(app, 'physical_key', side_effect=self.state({'Key.f8'})):
            app.reconcile_hotkeys()
        app.start_recording.assert_not_called()
        app.capture = (MagicMock(), set())
        with patch.object(app, 'physical_key') as read:
            app.reconcile_hotkeys()
        read.assert_not_called()

    def test_handler_error_does_not_kill_event_loop(self):
        app = self.make_app()
        app.events.put(('key', (True, keyboard.Key.f8)))
        app.events.put(('reconnect', None))
        with patch.object(app, 'handle_key', side_effect=RuntimeError('private data')):
            app.poll()
        app.root.after.assert_called_once_with(30, app.poll)
        self.assertNotIn('private data', app.status.set.call_args.args[0])
        with patch.object(app, 'physical_key', side_effect=self.state(set())):
            app.poll()
        app.start_listener.assert_called_once()
        self.assertEqual(app.root.after.call_count, 2)

    def test_idle_does_not_restart_a_healthy_listener(self):
        app = self.make_app()
        with patch.object(app, 'physical_key', side_effect=self.state(set())):
            for _ in range(100):
                app.reconcile_hotkeys()
        app.start_listener.assert_not_called()
        app.start_recording.assert_not_called()
