import unittest
from unittest.mock import Mock
from manual_graphics.lifecycle import GitHub


def response(status, data):
    value = Mock(status_code=status, content=b'json')
    value.json.return_value = data
    return value


class RunIdentityTests(unittest.TestCase):
    def test_old_attempt_is_not_active_during_rerun(self):
        http = Mock()
        http.request.return_value = response(200, {'status': 'in_progress', 'run_attempt': 2})
        api = GitHub('test', 'owner/repo', http)
        self.assertFalse(api.run_active('22', attempt=1))
        self.assertTrue(api.run_active('22', attempt=2))

    def test_deleted_run_requires_verified_actions_access(self):
        http = Mock()
        http.request.side_effect = [response(404, {}), response(200, {'workflow_runs': []})]
        self.assertFalse(GitHub('test', 'owner/repo', http).run_active('22'))
        self.assertEqual(http.request.call_count, 2)

    def test_hidden_or_inaccessible_runs_fail_closed(self):
        for status in (403, 404, 500):
            http = Mock()
            http.request.side_effect = [response(404, {}), response(status, {})]
            with self.assertRaises(RuntimeError):
                GitHub('test', 'owner/repo', http).run_active('22')
