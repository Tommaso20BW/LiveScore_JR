import unittest
from unittest.mock import Mock
import requests
from manual_graphics.telegram import Telegram, DeliveryUncertain, TelegramError
from manual_graphics.store import GistStore, StorageError


class TransportTests(unittest.TestCase):
    def test_gist_error_identifies_file_and_retry_without_response_body(self):
        http = Mock()
        http.get.return_value.status_code = 200
        http.get.return_value.json.return_value = {'public': False, 'files': {}}
        http.patch.return_value.status_code = 429
        http.patch.return_value.headers = {'Retry-After': '120'}
        http.patch.return_value.text = 'secret-content'
        with self.assertRaises(StorageError) as caught:
            GistStore('secret-token', 'gist', http).write('session', {'status': 'ready'})
        self.assertIn('manual_session.json', str(caught.exception))
        self.assertEqual(caught.exception.retry_after, 120)
        self.assertNotIn('secret', str(caught.exception))

    def test_document_keeps_original_bytes_and_private_destination(self):
        http = Mock()
        http.post.return_value.status_code = 200
        http.post.return_value.json.return_value = {'ok': True, 'result': {'message_id': 12}}
        tg = Telegram('token', '7', http)
        png = b'\x89PNG\r\n\x1a\noriginal'
        self.assertEqual(tg.document(png), 12)
        self.assertEqual(http.post.call_args.kwargs['files']['document'][1], png)
        self.assertEqual(http.post.call_args.kwargs['data'], {'chat_id': '7'})

    def test_timeout_is_uncertain_not_safe_retry(self):
        http = Mock()
        http.post.side_effect = requests.Timeout('token must not leak')
        with self.assertRaises(DeliveryUncertain) as error:
            Telegram('secret', '7', http).document(b'\x89PNG\r\n\x1a\n')
        self.assertNotIn('token must not leak', str(error.exception))

    def test_public_gist_never_written(self):
        http = Mock()
        http.get.return_value.status_code = 200
        http.get.return_value.json.return_value = {'public': True, 'files': {}}
        with self.assertRaises(StorageError):
            GistStore('secret', 'gist', http).write('receiver', {'offset': 3})
        http.patch.assert_not_called()

    def test_only_owned_gist_file_is_patched(self):
        http = Mock()
        http.get.return_value.status_code = 200
        http.get.return_value.json.return_value = {'public': False, 'files': {'match_state.json': {}}}
        http.patch.return_value.status_code = 200
        GistStore('secret', 'gist', http).write('receiver', {'offset': 3})
        self.assertEqual(set(http.patch.call_args.kwargs['json']['files']), {'manual_receiver.json'})

    def test_unknown_document_response_is_uncertain(self):
        http = Mock()
        http.post.return_value.status_code = 200
        http.post.return_value.json.side_effect = ValueError('invalid JSON')
        with self.assertRaises(DeliveryUncertain):
            Telegram('secret', '7', http).document(b'\x89PNG\r\n\x1a\n')
