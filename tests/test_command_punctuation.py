import unittest
from copy import deepcopy
from amber_core import DEFAULT_CONFIG, clean_text


class CommandPunctuationTests(unittest.TestCase):
    def test_command_separators(self):
        examples = {
            'Hallo, neuer Absatz, Weiter.': 'Hallo\n\nWeiter.',
            'Hallo, neue Zeile Weiter.': 'Hallo\nWeiter.',
            'Hallo. Neue Zeile, Weiter.': 'Hallo.\nWeiter.',
            'Liste, Stichpunkt, Brot': 'Liste\n• Brot',
            'Das ist Anführungszeichen auf, eine gute Idee, Anführungszeichen zu.': 'Das ist „eine gute Idee“.',
            'Anführungszeichen auf Hallo Anführungszeichen zu,': '„Hallo“',
            'Anführungszeichen auf Hallo Anführungszeichen zu,.': '„Hallo“.',
            'Er sagt: Anführungszeichen auf Ja, gerne, Anführungszeichen zu, und geht.': 'Er sagt: „Ja, gerne“, und geht.',
            'Ja, gerne.': 'Ja, gerne.',
            'Hallo, neue Zeilen bleiben Wörter.': 'Hallo, neue Zeilen bleiben Wörter.',
            'A, neue Zeile, neue Zeile B': 'A\n\nB',
        }
        for smart in (True, False):
            config = deepcopy(DEFAULT_CONFIG)
            config['smart_cleanup'] = smart
            for source, expected in examples.items():
                with self.subTest(source=source, smart=smart):
                    self.assertEqual(clean_text(source, config), expected)

    def test_custom_command_and_disabled_command(self):
        config = deepcopy(DEFAULT_CONFIG)
        config['replacements'] = {'Absatz bitte': '\n\n'}
        self.assertEqual(clean_text('A, Absatz bitte, B', config), 'A\n\nB')
        self.assertEqual(clean_text('A, neue Zeile, B', config), 'A, neue Zeile, B')

    def test_legacy_bullet_spacing(self):
        for replacement in ("\n•", "\n• ", "\n•   "):
            for smart in (True, False):
                config = deepcopy(DEFAULT_CONFIG)
                config['smart_cleanup'] = smart
                config['replacements']['Stichpunkt'] = replacement
                self.assertEqual(clean_text('Liste, Stichpunkt, Brot Stichpunkt Milch', config), 'Liste\n• Brot\n• Milch')
