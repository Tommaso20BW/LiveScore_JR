import unittest
from unittest.mock import Mock, patch
import juve_bot_espn as bot

class CanvaTokenCacheTests(unittest.TestCase):
    def test_valid_token_reused_and_expired_token_refreshed(self):
        response=Mock(status_code=200)
        response.json.return_value={'access_token':'access','expires_in':14400,'refresh_token':'rotated'}
        with patch.object(bot,'_CANVA_ACCESS_TOKEN',None), \
             patch.object(bot,'_CANVA_ACCESS_EXPIRES_AT',0), \
             patch.object(bot,'CANVA_REFRESH_TOKEN','initial'), \
             patch.object(bot.SESSION,'post',return_value=response) as post, \
             patch.object(bot,'update_github_secret',return_value=True) as update, \
             patch.object(bot.time,'monotonic',return_value=100) as clock:
            for _ in range(5):
                self.assertEqual(bot.get_valid_token(),'access')
            self.assertEqual(post.call_count,1)
            update.assert_called_once_with('CANVA_REFRESH_TOKEN','rotated')
            clock.return_value=20000
            self.assertEqual(bot.get_valid_token(),'access')
            self.assertEqual(post.call_count,2)

    def test_failure_is_not_cached(self):
        with patch.object(bot,'_CANVA_ACCESS_TOKEN',None), \
             patch.object(bot,'CANVA_REFRESH_TOKEN','initial'), \
             patch.object(bot.SESSION,'post',return_value=Mock(status_code=503,text='unavailable')) as post:
            self.assertIsNone(bot.get_valid_token())
            self.assertIsNone(bot.get_valid_token())
            self.assertEqual(post.call_count,2)
