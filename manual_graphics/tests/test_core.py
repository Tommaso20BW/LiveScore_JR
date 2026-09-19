import copy
import unittest
from manual_graphics.conversation import parse_minute, parse_score, parse_stat_pair, Wizard
from manual_graphics.coordination import Coordinator
from manual_graphics.telegram import authorized
from manual_graphics.lifecycle import cleanup_completed


class MemoryStore:
    def __init__(self):
        self.data = {}
    def read(self, name):
        return copy.deepcopy(self.data.get(name, {}))
    def write(self, name, data):
        self.data[name] = copy.deepcopy(data)


def message(text, sender=7, chat=7):
    return {'update_id': 20, 'message': {'from': {'id': sender},
            'chat': {'id': chat, 'type': 'private'}, 'text': text}}


class CoreTests(unittest.TestCase):
    def test_rerun_requires_fresh_acknowledgement(self):
        store = MemoryStore()
        old = Coordinator(store, '22', lambda _: True)
        old.request()
        live = Coordinator(store, '11', lambda _: True)
        live.live_paused(40)
        old.finish(41)
        new = Coordinator(store, '22', lambda _: True)
        new.request()
        self.assertFalse(new.ready(['11']))
        live.live_paused(41)
        self.assertTrue(new.ready(['11']))

    def test_authorization(self):
        self.assertTrue(authorized(message('/grafica'), 7, 7))
        self.assertFalse(authorized(message('/grafica', sender=8), 7, 7))
        self.assertFalse(authorized(message('/grafica', chat=8), 7, 7))
        value = message('/grafica')
        value['message']['chat']['type'] = 'group'
        self.assertFalse(authorized(value, 7, 7))

    def test_minutes(self):
        self.assertEqual(parse_minute("90+12'"), '90+12')
        self.assertEqual(parse_minute('56'), '56')
        for value in ['-2', 'abc', '120+100', '999', '2;exit']:
            with self.assertRaises(ValueError):
                parse_minute(value)

    def test_scores_and_missing_stats(self):
        self.assertEqual(parse_score('2-1'), (2, 1))
        self.assertEqual(parse_stat_pair('0-0'), ('0', '0'))
        self.assertEqual(parse_stat_pair('1,72 / 0,95'), ('1.72', '0.95'))
        self.assertIsNone(parse_stat_pair('-'))
        for value in ['NaN-0', '-1-0', 'inf/1']:
            with self.assertRaises(ValueError):
                parse_stat_pair(value)

    def test_manual_waits_for_live_ack_and_returns_control(self):
        store = MemoryStore()
        manual = Coordinator(store, '22', lambda _: True)
        manual.request()
        self.assertFalse(manual.ready(['11']))
        live = Coordinator(store, '11', lambda _: True)
        self.assertTrue(live.live_paused(40))
        self.assertTrue(manual.ready(['11']))
        manual.finish(51)
        self.assertFalse(live.live_paused(40))
        self.assertEqual(store.read('receiver')['offset'], 51)

    def test_crashed_manual_does_not_disable_live_forever(self):
        store = MemoryStore()
        Coordinator(store, '22', lambda _: True).request()
        live = Coordinator(store, '11', lambda _: False)
        self.assertFalse(live.live_paused(3))

    def test_cleanup_only_own_completed_previous_runs(self):
        deleted = []
        class API:
            def runs(self, workflow):
                return [dict(id=1, status='completed', workflow_id=5),
                        dict(id=2, status='in_progress', workflow_id=5),
                        dict(id=3, status='completed', workflow_id=9),
                        dict(id=4, status='completed', workflow_id=5)]
            def delete(self, run):
                deleted.append(run)
        self.assertEqual(cleanup_completed(API(), 5, 4), [1])
        self.assertEqual(deleted, [1])
