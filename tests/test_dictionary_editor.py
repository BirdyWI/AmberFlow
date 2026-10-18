import tkinter as tk
import unittest
from copy import deepcopy
from amber_core import DEFAULT_CONFIG, clean_text, ConfigError
from dictionary_editor import DictionaryEditor


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.editor = DictionaryEditor(self.root, ['Kundendienst'], {'neue Zeile': '\n'})

    def tearDown(self):
        self.root.destroy()

    def test_quotes(self):
        for smart in (True, False):
            config = deepcopy(DEFAULT_CONFIG)
            config['smart_cleanup'] = smart
            self.assertEqual(clean_text('Das ist Anführungszeichen auf eine gute Idee Anführungszeichen zu.', config), 'Das ist „eine gute Idee“.')
            self.assertEqual(clean_text('Anführungszeichen auf: Hallo Anführungszeichen zu', config), '„Hallo“')

    def test_add_edit_remove_and_pending_save(self):
        e = self.editor
        e.spoken.insert(0, 'Anführungszeichen auf')
        e.written.insert('1.0', '„')
        self.assertEqual(e.get()[1]['Anführungszeichen auf'], '„')
        e.new()
        e.table.selection_set('neue Zeile')
        e.select()
        self.assertEqual(e.written.get('1.0', 'end-1c'), '\n')
        e.written.delete('1.0', 'end')
        e.written.insert('1.0', '\n\n')
        self.assertEqual(e.get()[1]['neue Zeile'], '\n\n')
        e.remove()
        self.assertNotIn('neue Zeile', e.get()[1])

    def test_duplicate_and_empty_commands(self):
        e = self.editor
        e.spoken.insert(0, 'NEUE ZEILE')
        with self.assertRaises(ConfigError):
            e.get()
        e.spoken.delete(0, 'end')
        e.written.insert('1.0', 'x')
        with self.assertRaises(ConfigError):
            e.get()

    def test_terms_and_literal_characters(self):
        e = self.editor
        e.spoken.insert(0, 'Zitat')
        e.written.insert('1.0', '"Hallo" \\ Text')
        terms, rows = e.get()
        self.assertEqual(terms, ['Kundendienst'])
        self.assertEqual(rows['Zitat'], '"Hallo" \\ Text')
