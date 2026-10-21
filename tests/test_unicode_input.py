import unittest
from unittest.mock import MagicMock, patch
from windows_desktop import type_unicode, TEXT_INPUT_MARKER
from test_app import app_fixture


class UnicodeInputTests(unittest.TestCase):
    def setUp(self):
        native = patch('windows_desktop.insert_native_editor', return_value=False)
        native.start()
        self.addCleanup(native.stop)

    def test_unicode_surrogates_and_line_breaks_are_sent_as_text(self):
        api = MagicMock()
        captured = []
        def send(count, events, size):
            captured.extend((e.ki.wVk, e.ki.wScan, e.ki.dwFlags, e.ki.dwExtraInfo) for e in events)
            return count
        api.SendInput.side_effect = send
        with patch('windows_desktop.user32', return_value=api):
            type_unicode('Grüße „ja“\r\n\n• 🧡')
        units = [item[1] for item in captured[::2]]
        text = b''.join(unit.to_bytes(2, 'little') for unit in units).decode('utf-16-le')
        self.assertEqual(text, 'Grüße „ja“\n\n• 🧡')
        self.assertTrue(all(item[0] == 0 and item[3] == TEXT_INPUT_MARKER for item in captured))
        self.assertTrue(all(item[2] == 4 for item in captured[::2]))
        self.assertTrue(all(item[2] == 6 for item in captured[1::2]))

    def test_partial_send_is_not_retried(self):
        api = MagicMock()
        api.SendInput.return_value = 1
        with patch('windows_desktop.user32', return_value=api), self.assertRaises(OSError):
            type_unicode('Hallo')
        api.SendInput.assert_called_once()

    def test_blocked_input_does_not_overwrite_clipboard(self):
        app = app_fixture()
        with patch('app.modifiers_down', return_value=False), patch('app.foreground_window', return_value=10), \
             patch('app.type_unicode', side_effect=OSError), patch('app.pyperclip.copy') as copy:
            app.deliver(1, 'Hallo', 10, True, '')
        copy.assert_not_called()
        app.show_result.assert_called_once()
        self.assertIsNone(app.pending_delivery)

    def test_injected_text_is_not_treated_as_a_shortcut(self):
        app = app_fixture()
        app.listener = None
        with patch('app.keyboard.Listener') as listener:
            app.start_listener()
        filter_event = listener.call_args.kwargs['win32_event_filter']
        self.assertFalse(filter_event(0, MagicMock(dwExtraInfo=TEXT_INPUT_MARKER)))
        self.assertTrue(filter_event(0, MagicMock(dwExtraInfo=0)))
