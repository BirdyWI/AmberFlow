import unittest
from paste_delivery import submit

class PasteTests(unittest.TestCase):
    def run_case(self, mutation=None, failure=False):
        state = dict(target=12, active=True, modifier=False, clipboard='old', pastes=0)
        def paste():
            state['pastes'] += 1
            if failure:
                raise OSError('partial shortcut')
        def wait(seconds):
            if mutation:
                state.update(mutation)
        args = ('A\n\nB\n• „Grüße“',12,lambda:state['target'],lambda:state['modifier'],
                lambda text:state.update(clipboard=text),lambda:state['clipboard'],paste,
                wait,lambda:state['active'])
        return state,args

    def test_multiline_payload_is_preserved(self):
        state,args=self.run_case()
        submit(*args)
        self.assertEqual(state['clipboard'],args[0])
        self.assertEqual(state['pastes'],1)

    def test_focus_cancel_modifiers_and_clipboard_races_do_not_paste(self):
        for change in ({'target':99},{'active':False},{'modifier':True},{'clipboard':'other'}):
            with self.subTest(change=change):
                state,args=self.run_case(change)
                with self.assertRaises(RuntimeError): submit(*args)
                self.assertEqual(state['pastes'],0)

    def test_invalid_initial_focus_does_not_touch_clipboard(self):
        state,args=self.run_case()
        state['target']=99
        with self.assertRaises(RuntimeError): submit(*args)
        self.assertEqual(state['clipboard'],'old')

    def test_failed_shortcut_is_not_retried(self):
        state,args=self.run_case(failure=True)
        with self.assertRaises(OSError): submit(*args)
        self.assertEqual(state['pastes'],1)

if __name__=='__main__': unittest.main()
