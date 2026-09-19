import unittest
from unittest.mock import Mock
from manual_graphics.service import Service
from manual_graphics.live_bridge import bridge_poll
from manual_graphics.tests.test_core import MemoryStore, message
from manual_graphics.telegram import TelegramError


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.tg = Mock()
        self.tg.poll.return_value = []
        self.service = Service(self.store, self.tg, Mock(), Mock(), owner_id=7, chat_id=7)

    def test_failed_prompt_is_retried_without_advancing_twice(self):
        self.store.write('receiver', {'pending': [message('/grafica')]})
        self.service.wizard.handle.return_value = ({'status': 'editing'}, [{'text': 'Scegli'}])
        self.tg.prompt.side_effect = [TelegramError('offline'), None]
        with self.assertRaises(TelegramError):
            self.service.conversations()
        self.service.conversations()
        self.service.wizard.handle.assert_called_once()
        self.assertEqual(self.tg.prompt.call_count, 2)
        self.assertEqual(self.store.read('receiver')['pending'], [])

    def test_successful_render_sends_one_original_document(self):
        png = b'\x89PNG\r\n\x1a\noriginal-payload'
        self.store.write('session', {'id': 'request', 'status': 'ready', 'data': {'kind': 'kick'}})
        self.service.renderer.render.return_value = png
        self.tg.document.return_value = 123
        self.service.rendering()
        self.service.worker.join(timeout=2)
        self.service.rendering()
        self.service.rendering()
        self.tg.document.assert_called_once_with(png, 'kick-request.png')
        self.assertEqual(self.store.read('session')['status'], 'completed')
        self.assertEqual(self.store.read('session')['message_id'], 123)

    def test_finished_render_survives_temporary_state_read_error(self):
        png = b'\x89PNG\r\n\x1a\npayload'
        self.store.write('session', {'id': 'request', 'status': 'rendering', 'data': {'kind': 'kick'}})
        self.service.results.put(('request', png, None))
        original = self.store.read
        self.store.read = Mock(side_effect=RuntimeError('Temporary storage failure'))
        with self.assertRaises(RuntimeError):
            self.service.rendering()
        self.store.read = original
        self.service.rendering()
        self.tg.document.assert_called_once_with(png, 'kick-request.png')

    def test_unauthorized_updates_never_reach_wizard(self):
        self.tg.poll.return_value = [message('/grafica', sender=8)]
        self.service.receive()
        self.assertEqual(self.store.read('receiver')['offset'], 21)
        self.assertEqual(self.store.read('receiver')['pending'], [])

    def test_kit_is_routed_without_waiting_for_render(self):
        self.tg.poll.return_value = [{'update_id': 50, 'callback_query': {
            'id': 'x', 'from': {'id': 7}, 'data': 'kit:match:home',
            'message': {'chat': {'id': 7, 'type': 'private'}}}}]
        self.service.receive()
        self.assertEqual(self.store.read('receiver')['kit'][0]['update_id'], 50)
        self.assertEqual(self.store.read('receiver')['pending'], [])

    def test_manual_and_live_updates_are_persisted_before_offset(self):
        self.tg.poll.return_value = [message('/grafica')]
        self.service.receive()
        state = self.store.read('receiver')
        self.assertEqual(state['offset'], 21)
        self.assertEqual(state['pending'][0]['message']['text'], '/grafica')

    def test_live_replays_queued_kit_even_after_manual_exit(self):
        self.store.write('receiver', {'offset': 60, 'kit': [{'update_id': 50, 'callback_query': {}}]})
        coordinator = Mock()
        coordinator.live_paused.return_value = False
        original = Mock()
        result = bridge_poll(self.store, coordinator, original, {'offset': 40})
        self.assertEqual(result.json()['result'][0]['update_id'], 50)
        original.assert_not_called()

    def test_live_resumes_at_saved_offset(self):
        self.store.write('receiver', {'offset': 60, 'kit': []})
        coordinator = Mock()
        coordinator.live_paused.return_value = False
        original = Mock()
        bridge_poll(self.store, coordinator, original, {'offset': 40})
        self.assertEqual(original.call_args.args[0]['offset'], 60)

    def test_live_does_not_poll_telegram_when_manual_owns_it(self):
        coordinator = Mock()
        coordinator.live_paused.return_value = True
        original = Mock()
        result = bridge_poll(self.store, coordinator, original, {})
        self.assertEqual(result.json()['result'], [])
        original.assert_not_called()

    def test_restart_marks_inflight_send_uncertain(self):
        self.store.write('session', {'status': 'sending', 'data': {'kind': 'goal'}})
        self.service.restore()
        self.assertEqual(self.store.read('session')['status'], 'uncertain')

    def test_restart_resumes_render_without_sending_stale_bytes(self):
        self.store.write('session', {'status': 'rendering', 'data': {'kind': 'goal'}})
        self.service.restore()
        self.assertEqual(self.store.read('session')['status'], 'ready')
