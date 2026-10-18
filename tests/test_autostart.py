import unittest
import uuid
from windows_desktop import acquire_instance, release_instance
from unittest.mock import patch, MagicMock
from autostart import set_autostart, startup_command, RUN_KEY, VALUE_NAME
from amber_core import validate_config, text_for_paste, ConfigError


class StartupTests(unittest.TestCase):
    def test_second_instance_is_prevented_and_lock_releases(self):
        name = "Local\\AmberFlow-test-" + uuid.uuid4().hex
        first = acquire_instance(name)
        try:
            self.assertIsNotNone(first)
            self.assertIsNone(acquire_instance(name))
        finally:
            release_instance(first)
        again = acquire_instance(name)
        self.assertIsNotNone(again)
        release_instance(again)

    def test_default_enabled_and_explicit_disable_preserved(self):
        self.assertTrue(validate_config({})["autostart"])
        self.assertFalse(validate_config({"autostart": False})["autostart"])
        with self.assertRaises(ConfigError):
            validate_config({"autostart": "yes"})

    def test_enable_sets_only_current_user_amberflow_value(self):
        with patch("autostart.winreg") as registry, patch("autostart.startup_command", return_value="quoted-command"):
            set_autostart(True)
            registry.CreateKeyEx.assert_called_once_with(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE)
            registry.SetValueEx.assert_called_once_with(registry.CreateKeyEx.return_value.__enter__.return_value,
                                                       VALUE_NAME, 0, registry.REG_SZ, "quoted-command")
            registry.DeleteValue.assert_not_called()

    def test_disable_removes_only_our_value(self):
        with patch("autostart.winreg") as registry:
            set_autostart(False)
            registry.DeleteValue.assert_called_once_with(registry.CreateKeyEx.return_value.__enter__.return_value, VALUE_NAME)
            registry.DeleteKey.assert_not_called()

    def test_disable_already_missing_is_ok(self):
        with patch("autostart.winreg") as registry:
            registry.DeleteValue.side_effect = FileNotFoundError
            set_autostart(False)

    def test_access_denied_is_reported(self):
        with patch("autostart.winreg.CreateKeyEx", side_effect=PermissionError), self.assertRaises(PermissionError):
            set_autostart(True)

    def test_command_quotes_spaces_and_uses_pythonw(self):
        with patch("autostart.Path.is_file", return_value=True):
            command = startup_command(r"C:\My Apps\AmberFlow\app.py", r"C:\Python Env\python.exe")
        self.assertEqual(command, '"C:\\Python Env\\pythonw.exe" "C:\\My Apps\\AmberFlow\\app.py" --autostart')


class SpacingTests(unittest.TestCase):
    def test_successive_dictations_have_separator(self):
        self.assertEqual(text_for_paste("Hallo.") + text_for_paste("Weiter."), "Hallo. Weiter. ")

    def test_preserve_existing_space_and_newline(self):
        for text in ("Hallo ", "Absatz\n\n", ""):
            self.assertEqual(text_for_paste(text), text)
