"""Native clipboard integration tests; synthetic data only, original restored.
No keyboard injection. Run while not manually copying clipboard content.
"""
import ctypes as C
import struct
import threading
import time
import tkinter as tk
import unittest
import os
from clipboard_tx import U, K, Snapshot, PasteTransaction, opened, put_bytes

@unittest.skipUnless(os.environ.get('AMBERFLOW_CLIPBOARD_TEST') == '1', 'Real clipboard test is opt-in')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()
        cls.hwnd = cls.root.winfo_id()
        with opened(cls.hwnd):
            cls.original = Snapshot.capture()
        cls.latest = U.GetClipboardSequenceNumber()

    @classmethod
    def tearDownClass(cls):
        with opened(cls.hwnd):
            if U.GetClipboardSequenceNumber() == cls.latest:
                cls.original.restore()
            else:
                print('External clipboard change detected; original NOT restored over newer content.')
        cls.original.close()
        cls.root.destroy()

    def write(self, items):
        with opened(self.hwnd):
            U.EmptyClipboard()
            for fmt, value in items:
                put_bytes(fmt, value)
        type(self).latest = U.GetClipboardSequenceNumber()

    def inspect(self):
        with opened(self.hwnd):
            snap = Snapshot.capture()
            result = dict(snap.items)
            snap.close()
        return result

    def read_text(self):
        with opened(self.hwnd):
            h = U.GetClipboardData(13)
            p = K.GlobalLock(h)
            try:
                return C.wstring_at(p)
            finally:
                K.GlobalUnlock(h)

    def setUp(self):
        self.write([(13, 'ORIGINAL\0'.encode('utf-16-le'))])

    def run_tx(self, inject=None, valid=lambda: True, timeout=.4):
        seen = []
        def consume():
            def worker():
                time.sleep(.03)
                seen.append(self.read_text())
            threading.Thread(target=worker).start()
        tx = PasteTransaction('Erster Satz.\n\nAbsatz.\n• Brot „Grüße“ 😀', valid,
                              inject or consume, timeout=timeout, grace=.08).start()
        end = time.monotonic() + 4
        while not tx.done.is_set() and time.monotonic() < end:
            self.root.update()
            time.sleep(.005)
        self.assertTrue(tx.done.is_set(), 'worker did not finish')
        type(self).latest = U.GetClipboardSequenceNumber()
        return tx, seen

    def test_read_and_restore(self):
        before = self.inspect()
        tx, seen = self.run_tx()
        self.assertEqual(tx.status, 'read_observed_restored', tx.error)
        self.assertEqual(seen, ['Erster Satz.\r\n\r\nAbsatz.\r\n• Brot „Grüße“ 😀'])
        self.assertEqual(self.inspect(), before)
        self.assertEqual(tx.text, '')

    def test_multiple_formats(self):
        html = U.RegisterClipboardFormatW('HTML Format')
        rtf = U.RegisterClipboardFormatW('Rich Text Format')
        # Valid 1x1 32-bit DIB and DROPFILES list; preserve opaque bytes exactly.
        dib = struct.pack('<IiiHHIIiiII', 40, 1, 1, 1, 32, 0, 4, 0, 0, 0, 0) + b'\x00\x00\xff\x00'
        drop = struct.pack('<IiiII', 20, 0, 0, 0, 1) + 'C:\\synthetic.txt\0\0'.encode('utf-16-le')
        self.write([(13, 'formatiert\0'.encode('utf-16-le')), (html, b'<b>formatiert</b>\0'),
                    (rtf, b'{\\rtf1 formatiert}\0'), (15, drop), (8, dib)])
        # Windows may synthesize CF_BITMAP when capturing the DIB. Handles differ.
        before = {k:v for k,v in self.inspect().items() if k != 2}
        tx, _ = self.run_tx()
        self.assertEqual(tx.status, 'read_observed_restored', tx.error)
        after = {k:v for k,v in self.inspect().items() if k != 2}
        self.assertEqual(after, before)

    def test_empty_clipboard(self):
        self.write([])
        tx, _ = self.run_tx()
        self.assertEqual(tx.status, 'read_observed_restored', tx.error)
        self.assertEqual(self.inspect(), {})

    def test_empty_enterprise_metadata_does_not_block_text(self):
        marker = U.RegisterClipboardFormatW('EnterpriseDataProtectionId')
        with opened(self.hwnd):
            C.set_last_error(0)
            U.SetClipboardData(marker, None)
            self.assertEqual(C.get_last_error(), 0)
        tx, seen = self.run_tx()
        self.assertEqual(tx.status, 'read_observed_restored', tx.error)
        self.assertEqual(len(seen), 1)
        self.assertEqual(self.read_text(), 'ORIGINAL')

    def test_new_copy_wins(self):
        def inject():
            self.write([(13, 'NEU\0'.encode('utf-16-le'))])
        tx, _ = self.run_tx(inject)
        self.assertEqual(tx.status, 'newer_clipboard_preserved', tx.error)
        self.assertEqual(self.read_text(), 'NEU')

    def test_same_text_new_copy_wins(self):
        def inject():
            self.write([(13, 'Erster Satz.\r\n\r\nAbsatz.\r\n• Brot „Grüße“ 😀\0'.encode('utf-16-le'))])
        tx, _ = self.run_tx(inject)
        self.assertEqual(tx.status, 'newer_clipboard_preserved', tx.error)

    def test_injection_failure_restores(self):
        def fail():
            raise OSError('synthetic')
        tx, _ = self.run_tx(fail)
        self.assertEqual(tx.status, 'injection_failed_restored', tx.error)
        self.assertEqual(self.read_text(), 'ORIGINAL')

    def test_no_reader_timeout(self):
        tx, _ = self.run_tx(lambda: None)
        self.assertEqual(tx.status, 'unconfirmed_timeout_restored', tx.error)
        self.assertEqual(self.read_text(), 'ORIGINAL')

    def test_cancel_before_publish(self):
        seq = U.GetClipboardSequenceNumber()
        tx, _ = self.run_tx(valid=lambda: False)
        self.assertEqual(tx.status, 'cancelled_before_publish')
        self.assertEqual(U.GetClipboardSequenceNumber(), seq)

    def test_unsupported_unchanged(self):
        self.write([(0x201, b'private\0')])
        seq = U.GetClipboardSequenceNumber()
        tx, _ = self.run_tx()
        self.assertEqual(tx.status, 'error')
        self.assertIn('Sonderformat', tx.error)
        self.assertEqual(U.GetClipboardSequenceNumber(), seq)

    def test_repeated_transactions(self):
        for _ in range(3):
            tx, _ = self.run_tx()
            self.assertEqual(tx.status, 'read_observed_restored', tx.error)
            self.assertEqual(self.read_text(), 'ORIGINAL')

if __name__ == '__main__':
    unittest.main(verbosity=2)
