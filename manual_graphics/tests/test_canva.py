import contextlib
import unittest
from unittest.mock import Mock
from manual_graphics.canva import TokenManager, GitMutex
from manual_graphics.tests.test_core import MemoryStore


class TokenTests(unittest.TestCase):
    def test_abandoned_lock_passes_owner_attempt_for_recovery(self):
        api = Mock()
        api.run_active.return_value = False
        mutex = GitMutex(api, '22', 'base', attempt=2)
        mutex._head = Mock(return_value=('old', 'tree', {'locked': True, 'run_id': '22', 'attempt': 1}))
        mutex._advance = Mock(return_value='new')
        self.assertIs(mutex.__enter__(), mutex)
        api.run_active.assert_called_once_with('22', attempt=1)
        mutex._advance.assert_called_once_with('old', 'tree', True)

    def test_cached_token_no_oauth(self):
        store = MemoryStore()
        store.write('canva', {'access_token': 'cached', 'expires_at': 1000})
        http = Mock()
        mutex = Mock(side_effect=AssertionError('Cached token must not acquire Git lock'))
        manager = TokenManager(store, mutex, http, 'id', 'secret', 'old', lambda v: True)
        self.assertEqual(manager.get(now=100), 'cached')
        http.post.assert_not_called()

    def test_rotated_refresh_saved_before_secret_sync(self):
        store = MemoryStore()
        seen = []
        http = Mock()
        http.post.return_value.status_code = 200
        http.post.return_value.json.return_value = {'access_token': 'new', 'refresh_token': 'rotated', 'expires_in': 3600}
        def sync(token):
            seen.append(store.read('canva')['refresh_token'])
            return False
        manager = TokenManager(store, contextlib.nullcontext, http, 'id', 'secret', 'old', sync)
        self.assertEqual(manager.get(now=100), 'new')
        self.assertEqual(seen, ['rotated'])
        self.assertEqual(store.read('canva')['expires_at'], 3640)
        self.assertFalse(store.read('canva')['secret_synced'])

    def test_latest_gist_refresh_wins_over_environment(self):
        store = MemoryStore()
        store.write('canva', {'refresh_token': 'latest'})
        http = Mock()
        http.post.return_value.status_code = 200
        http.post.return_value.json.return_value = {'access_token': 'new', 'expires_in': 3600}
        manager = TokenManager(store, contextlib.nullcontext, http, 'id', 'secret', 'stale', lambda v: True)
        manager.get(now=100)
        self.assertEqual(http.post.call_args.kwargs['data']['refresh_token'], 'latest')

    def test_failed_refresh_does_not_return_expired_access(self):
        store = MemoryStore()
        store.write('canva', {'access_token': 'expired', 'expires_at': 1})
        http = Mock()
        http.post.return_value.status_code = 400
        manager = TokenManager(store, contextlib.nullcontext, http, 'id', 'secret', 'old', lambda v: True)
        with self.assertRaises(RuntimeError):
            manager.get(now=100)
