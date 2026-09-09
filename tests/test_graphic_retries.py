import unittest
from unittest.mock import Mock, patch
import juve_bot_espn as bot


class GraphicRetryTests(unittest.TestCase):
    def test_edit_failures_stop_at_five(self):
        factory = Mock(return_value=b'png')
        with patch.object(bot, 'edit_telegram_goal_photo', return_value=False) as edit:
            self.assertEqual(bot._retry_graphic_on_text(42, 'text', factory, 'GOAL'), (42, False))
        self.assertEqual(factory.call_count, 5)
        self.assertEqual(edit.call_count, 5)

    def test_successful_initial_photo_does_not_retry(self):
        factory = Mock()
        response = Mock(status_code=200)
        response.json.return_value = {'result': {'message_id': 42}}
        with patch.object(bot, '_tg_post', return_value=response), \
             patch.object(bot, 'send_telegram_get_id') as send:
            self.assertEqual(bot.send_telegram_goal_get_id('text', b'png', retry_factory=factory), (42, True))
        factory.assert_not_called()
        send.assert_not_called()

    def test_generation_recovers_on_fifth_attempt_same_message(self):
        factory = Mock(side_effect=[None, None, None, None, b'png'])
        with patch.object(bot, 'send_telegram_get_id', return_value=42) as send, \
             patch.object(bot, 'edit_telegram_goal_photo', return_value=True) as edit:
            result = bot.send_telegram_goal_get_id('original', None, retry_factory=factory)
        self.assertEqual(result, (42, True))
        self.assertEqual(factory.call_count, 5)
        send.assert_called_once_with('original')
        edit.assert_called_once_with(42, 'original', b'png')

    def test_exhausted_attempts_leave_text_untouched(self):
        factory = Mock(side_effect=ValueError('render failed'))
        with patch.object(bot, 'edit_telegram_goal_photo') as edit, \
             patch.object(bot, 'delete_telegram_message') as delete:
            self.assertEqual(bot._retry_graphic_on_text(42, 'text', factory, 'GOAL'), (42, False))
        self.assertEqual(factory.call_count, 5)
        edit.assert_not_called()
        delete.assert_not_called()

    def test_upload_failure_regenerates_then_edits(self):
        factory = Mock(return_value=b'new')
        with patch.object(bot, '_tg_post', return_value=Mock(status_code=400)), \
             patch.object(bot, 'send_telegram_get_id', return_value=42) as send, \
             patch.object(bot, 'edit_telegram_goal_photo', side_effect=[False, True]) as edit:
            result = bot.send_telegram_saved_get_id('caption', b'old', retry_factory=factory)
        self.assertEqual(result, (42, True))
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(edit.call_count, 2)
        send.assert_called_once()

    def test_no_text_delivery_means_no_retries(self):
        factory = Mock()
        self.assertEqual(bot._retry_graphic_on_text(None, 'text', factory, 'GOAL'), (None, False))
        factory.assert_not_called()

    def test_phase_recovery_and_friendly_exclusion(self):
        args = dict(kind='half', data_espn={}, home_id='111', away_id='110',
                    home_name='Juventus', away_name='Inter', league_slug='ita.1', league_name='Serie A')
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'build_phase_graphic', side_effect=[None, b'png']) as build, \
             patch.object(bot, 'send_telegram_get_id', return_value=42), \
             patch.object(bot, 'edit_telegram_goal_photo', return_value=True):
            self.assertEqual(bot.send_phase_message('text', **args), 42)
            self.assertEqual(build.call_count, 2)
        args['league_slug'] = 'club.friendly'
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'build_phase_graphic', return_value=None) as build, \
             patch.object(bot, 'send_telegram_get_id', return_value=42), \
             patch.object(bot, 'edit_telegram_goal_photo') as edit:
            bot.send_phase_message('text', **args)
            build.assert_called_once()
            edit.assert_not_called()
