"""Opt-in Windows tests against an isolated Tk text field, never another app.

Run with AMBERFLOW_DESKTOP_TEST=1 on an interactive desktop. These tests briefly
focus their own window and preserve/restore the current text clipboard.
"""
import os
import ctypes
from ctypes import wintypes
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import pyperclip
from app import AmberFlowApp, foreground_window
from amber_core import ConfigStore
from windows_desktop import window_handle, modifiers_down


@unittest.skipUnless(os.environ.get("AMBERFLOW_DESKTOP_TEST") == "1", "Interactive desktop test is opt-in")
class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.patches = [
            patch("app.ConfigStore", return_value=ConfigStore(Path(self.tmp.name) / "config.json")),
            patch("app.AmberFlowApp.load_model", lambda instance: setattr(instance, "loading", True)),
            patch("app.keyboard.Listener"), patch("app.keyboard.Controller"), patch("app.pystray.Icon"),
            patch("app.sd.query_devices", return_value=[]), patch("app.set_autostart"), patch("app.migrate_legacy_autostart"),
        ]
        for context in self.patches:
            context.start()
        self.app = AmberFlowApp(self.root)
        self.target = None

    def pump(self, seconds=.15):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.root.update()
            if self.target is not None:
                self.target.update()
            time.sleep(.005)

    def target_field(self):
        self.app.settings.destroy()
        self.app.settings = None
        self.app.loading = False
        self.target = tk.Tk()
        self.target.title("AmberFlow – isolierter Eingabetest")
        self.target.geometry("500x160")
        field = tk.Text(self.target)
        field.pack(fill="both", expand=True)
        self.target.update()
        self.target.lift()
        field.focus_force()
        api = ctypes.windll.user32
        api.SetForegroundWindow.argtypes = [wintypes.HWND]
        api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        foreground_thread = api.GetWindowThreadProcessId(foreground_window(), None)
        current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        attached = api.AttachThreadInput(current_thread, foreground_thread, True)
        try:
            api.SetForegroundWindow(window_handle(self.target))
            field.focus_force()
        finally:
            if attached:
                api.AttachThreadInput(current_thread, foreground_thread, False)
        self.pump()
        handle = window_handle(self.target)
        self.assertEqual(foreground_window(), handle, "Testfenster nicht aktiv; keine Eingabe gesendet")
        self.assertFalse(modifiers_down(), "Steuertaste physisch gedrückt; keine Eingabe gesendet")
        return field, handle

    def tearDown(self):
        self.app.shutdown()
        if self.target is not None:
            self.target.destroy()
        for context in reversed(self.patches):
            context.stop()
        self.tmp.cleanup()

    def test_start_opens_settings_while_model_loads_and_hides_hud(self):
        self.pump()
        self.assertTrue(self.app.loading)
        self.assertTrue(self.app.settings.winfo_viewable())
        self.assertFalse(self.root.winfo_viewable())
        self.assertEqual(self.app.settings.cget("background"), "#18181b")
        for child in self.app.settings.winfo_children():
            self.assertLessEqual(child.winfo_y() + child.winfo_height(), self.app.settings.winfo_height())

    def test_hud_is_recording_only_and_does_not_take_focus(self):
        _, target = self.target_field()
        self.app.recording = True
        self.app.show_status("Aufnahme …")
        self.pump()
        self.assertTrue(self.root.winfo_viewable())
        self.assertEqual(foreground_window(), target)
        self.app.current_rms = .8
        self.app.update_meter()
        coords = self.app.canvas.coords(self.app.bars[2])
        self.assertGreater(coords[3] - coords[1], 4)
        self.assertEqual(self.app.canvas.itemcget(self.app.dot, "fill"), "#ef4444")
        self.app.recording = False
        self.app.busy = True
        self.app.show_status("Verarbeite …")
        self.pump(.15)
        self.assertTrue(self.root.winfo_viewable())
        self.assertEqual(self.app.canvas.itemcget(self.app.dot, "fill"), "#f59e0b")
        self.app.busy = False
        self.app.show_status("Fertig", visible=False)
        self.assertFalse(self.root.winfo_viewable())
        self.assertEqual(foreground_window(), target)

    def test_native_paste_reaches_the_text_field_without_review_window(self):
        field, target = self.target_field()
        previous = pyperclip.paste()
        sample = "AmberFlow Einfügetest: Grüße.\nZweite Zeile."
        try:
            self.app.deliver(self.app.job_id, sample, target, True, "")
            self.pump(.45)
            self.assertEqual(field.get("1.0", "end-1c"), sample + " ")
            self.app.deliver(self.app.job_id, "Nächster Satz.", target, True, "")
            self.pump(.2)
            self.assertEqual(field.get("1.0", "end-1c"), sample + " Nächster Satz. ")
            self.assertIsNone(self.app.result_window)
            self.assertFalse(self.root.winfo_viewable())
        finally:
            if pyperclip.paste() in (sample + " ", "Nächster Satz. "):
                pyperclip.copy(previous)


if __name__ == "__main__":
    unittest.main()
