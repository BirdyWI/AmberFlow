import ctypes
import unittest
from unittest.mock import MagicMock, patch
from windows_desktop import insert_native_editor, type_unicode


class NativeEditorTests(unittest.TestCase):
    def api(self, name='RichEditD2DPT'):
        api = MagicMock()
        api.GetForegroundWindow.return_value = 10
        api.GetAncestor.return_value = 10
        api.GetWindowThreadProcessId.return_value = 30
        def info(thread, pointer):
            pointer._obj.hwndFocus = 20
            return 1
        def class_name(handle, buffer, size):
            buffer.value = name
            return len(name)
        api.GetGUIThreadInfo.side_effect = info
        api.GetClassNameW.side_effect = class_name
        api.SendMessageTimeoutW.return_value = 1
        return api

    def test_notepad_replaces_selection_with_undo_and_crlf(self):
        api = self.api()
        captured = []
        def send(hwnd, message, undo, value, flags, timeout, result):
            captured.append((hwnd, message, undo, ctypes.wstring_at(value)))
            return 1
        api.SendMessageTimeoutW.side_effect = send
        with patch('windows_desktop.user32', return_value=api):
            type_unicode('Grüße\r\n\n„Text“ 🧡')
        self.assertEqual(captured, [(20, 0xC2, 1, 'Grüße\r\n\r\n„Text“ 🧡')])
        api.SendInput.assert_not_called()

    def test_other_editor_uses_fallback(self):
        api = self.api('Chrome_RenderWidgetHostHWND')
        with patch('windows_desktop.user32', return_value=api):
            self.assertFalse(insert_native_editor('Text'))
        api.SendMessageTimeoutW.assert_not_called()

    def test_timeout_never_replays_via_keyboard(self):
        api = self.api()
        api.SendMessageTimeoutW.return_value = 0
        with patch('windows_desktop.user32', return_value=api), self.assertRaises(OSError):
            type_unicode('Text')
        api.SendInput.assert_not_called()

    def test_changed_foreground_aborts(self):
        api = self.api()
        api.GetForegroundWindow.side_effect = [10, 11]
        with patch('windows_desktop.user32', return_value=api), self.assertRaises(OSError):
            insert_native_editor('Text')
        api.SendMessageTimeoutW.assert_not_called()

    def test_different_root_aborts(self):
        api = self.api()
        api.GetAncestor.return_value = 11
        with patch('windows_desktop.user32', return_value=api), self.assertRaises(OSError):
            insert_native_editor('Text')
        api.SendMessageTimeoutW.assert_not_called()
