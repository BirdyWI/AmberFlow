import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from amber_core import ConfigStore, DEFAULT_CONFIG
from autostart import migrate_legacy_autostart


class RenameTests(unittest.TestCase):
    def test_old_config_is_read_and_saved_under_new_name(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            old = Path(folder) / 'ArgonFlow' / 'config.json'
            old.parent.mkdir()
            data = dict(DEFAULT_CONFIG, auto_paste=False, prompt_terms=['ExistingTerm'])
            old.write_text(json.dumps(data), encoding='utf-8')
            original = old.read_bytes()
            store = ConfigStore()
            actual, warning = store.load()
            self.assertFalse(actual['auto_paste'])
            self.assertEqual(actual['prompt_terms'], ['ExistingTerm'])
            self.assertTrue(warning)
            store.save(actual)
            self.assertEqual(old.read_bytes(), original)
            self.assertEqual(store.path.parent.name, 'AmberFlow')
            self.assertTrue(store.path.is_file())
            self.assertEqual(store.load()[1], '')

    def test_new_config_takes_priority(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'LOCALAPPDATA': folder}):
            old = Path(folder) / 'ArgonFlow' / 'config.json'
            old.parent.mkdir()
            old.write_text('broken legacy config', encoding='utf-8')
            store = ConfigStore()
            store.save(DEFAULT_CONFIG)
            self.assertEqual(store.load()[0], DEFAULT_CONFIG)

    def test_only_matching_legacy_startup_is_removed(self):
        for existing, expected in [('same-command', True), ('another-installation', False)]:
            with patch('autostart.winreg') as registry, patch('autostart.startup_command', return_value='same-command'):
                registry.QueryValueEx.return_value = (existing, 1)
                migrate_legacy_autostart()
                self.assertEqual(registry.DeleteValue.called, expected)
                if expected:
                    self.assertEqual(registry.DeleteValue.call_args.args[1], 'ArgonFlow')
