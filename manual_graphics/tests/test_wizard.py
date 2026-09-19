import unittest
from manual_graphics.conversation import Wizard
from manual_graphics.catalog import Catalog
from manual_graphics.tests.test_core import message


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.wizard = Wizard(Catalog())

    def answer(self, state, text):
        return self.wizard.handle(state, message(text), 100)[0]

    def test_goal_complete_and_resume(self):
        state = self.answer({}, '/grafica')
        for answer in ['1', '1', '1', '2', 'Inter', 'Yildiz', '90+12', '1', '2-1']:
            state = self.answer(state, answer)
        self.assertEqual(state['step'], 'confirm')
        self.assertEqual(state['data']['side'], 'away')
        self.assertEqual(state['data']['minute'], '90+12')
        state = self.answer(state, '1')
        self.assertEqual(state['status'], 'ready')

    def test_old_callback_does_not_advance_form(self):
        state = self.answer({}, '/grafica')
        callback = {'callback_query': {'data': 'mg:old:0:0'}}
        after, effects = self.wizard.handle(state, callback, 100)
        self.assertEqual(after, state)
        self.assertIn('scaduto', effects[0]['text'])

    def test_invalid_input_does_not_advance(self):
        state = self.answer({}, '/grafica')
        after = self.answer(state, '500')
        self.assertEqual(after['step'], 'kind')

    def test_cancel(self):
        state = self.answer({}, '/grafica')
        state = self.answer(state, '/annulla')
        self.assertEqual(state['status'], 'cancelled')

    def test_expired_session_is_not_silently_reused(self):
        state = self.answer({}, '/grafica')
        after, _ = self.wizard.handle(state, message('1'), 2001)
        self.assertEqual(after['status'], 'expired')

    def test_stats_zero_and_missing(self):
        state = self.answer({}, '/grafica')
        for answer in ['7', '1', '2', '1', 'Inter', '3']:
            state = self.answer(state, answer)
        for answer in ['57-43', '-', '0-0'] + ['-'] * 9:
            state = self.answer(state, answer)
        self.assertEqual(state['step'], 'confirm')
        self.assertEqual(state['data']['rows'], [('POSSESSO', '57%', '43%'), ('TIRI', '0', '0')])
