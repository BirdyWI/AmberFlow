"""Regression for Notepad's unreadable EnterpriseDataProtectionId marker.
All handles and API results mocked: never modifies the real clipboard.
"""
import ctypes as C
import unittest
from unittest.mock import patch, MagicMock
import clipboard_tx as tx

class MetadataTests(unittest.TestCase):
    def test_confirmed_empty_marker_is_omitted_but_text_is_saved(self):
        data = 'Kontrolltext\0'.encode('utf-16-le')
        memory = C.create_string_buffer(data)
        with patch.object(tx, 'U') as u, patch.object(tx, 'K') as k, patch.object(tx, 'empty_enterprise_marker', return_value=True) as check:
            u.EnumClipboardFormats.side_effect = [49337, 13, 0]
            u.GetClipboardData.side_effect = [None, 123]
            k.GlobalSize.return_value = len(data)
            k.GlobalLock.return_value = C.addressof(memory)
            saved = tx.Snapshot.capture()
            self.assertEqual(saved.items, [(13, data)])
            check.assert_called_once_with(49337)
            u.EmptyClipboard.assert_not_called()

    def test_unverified_or_protected_marker_aborts_without_changes(self):
        with patch.object(tx, 'U') as u, patch.object(tx, 'empty_enterprise_marker', return_value=False):
            u.EnumClipboardFormats.side_effect = [49337]
            u.GetClipboardData.return_value = None
            with self.assertRaises(tx.ClipboardError):
                tx.Snapshot.capture()
            u.EmptyClipboard.assert_not_called()

    def test_other_unreadable_formats_are_not_ignored(self):
        def name(fmt, buf, size):
            buf.value = 'SomeOtherFormat'
            return len(buf.value)
        with patch.object(tx.U, 'GetClipboardFormatNameW', side_effect=name), patch.object(tx.C, 'WinDLL') as library:
            self.assertFalse(tx.empty_enterprise_marker(50001))
            library.assert_not_called()

    def edp_result(self, result, pointer=None):
        def name(fmt, buf, size):
            buf.value = 'EnterpriseDataProtectionId'
            return len(buf.value)
        def query(out):
            C.cast(out, C.POINTER(tx.PTR))[0] = pointer
            return result
        return name, query

    def test_windows_success_and_null_identity_is_required(self):
        for hr, pointer, expected in [(0, None, True), (-1, None, False), (0, 123, False), (1, None, False)]:
            with self.subTest(hr=hr, pointer=pointer):
                name, query = self.edp_result(hr, pointer)
                with patch.object(tx.U, 'GetClipboardFormatNameW', side_effect=name), patch.object(tx.C, 'WinDLL') as lib, patch.object(tx.K, 'HeapFree') as free:
                    lib.return_value.EdpGetEnterpriseIdForClipboard.side_effect = query
                    self.assertEqual(tx.empty_enterprise_marker(49337), expected)
                    self.assertEqual(free.called, bool(pointer))

    def test_missing_edp_api_keeps_fail_closed_behavior(self):
        name, _ = self.edp_result(0)
        with patch.object(tx.U, 'GetClipboardFormatNameW', side_effect=name), patch.object(tx.C, 'WinDLL', side_effect=OSError):
            self.assertFalse(tx.empty_enterprise_marker(49337))
