import threading
import time
import unittest
from unittest.mock import Mock, patch

from livescore import settings
from livescore.state import gist

REAL_SLEEP = time.sleep      # setUp sostituisce time.sleep (e' lo stesso modulo usato da gist)


def _response(code=200):
    r = Mock()
    r.status_code = code
    return r


class BackgroundSaveTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(settings, "GH_PAT", "x" * 10), patch.object(settings, "GIST_ID", "g1"),
                        patch.object(gist.time, "sleep", lambda s: None)]
        for p in self.patches:
            p.start()
        gist.flush()
        gist.take_async_failure()

    def tearDown(self):
        gist.flush()
        for p in self.patches:
            p.stop()

    def test_background_save_returns_before_github_answers(self):
        release = threading.Event()
        calls = []

        def slow_patch(*a, **k):
            calls.append(k["json"])
            release.wait(5)
            return _response()

        with patch.object(gist.net.SESSION, "patch", slow_patch):
            started = time.monotonic()
            with gist.background():
                self.assertTrue(gist.salva_stato_su_gist({"a": 1}))
            self.assertLess(time.monotonic() - started, 1.0)
            release.set()
            self.assertTrue(gist.flush(5))
        self.assertEqual(len(calls), 1)

    def test_only_latest_state_is_written_when_saves_pile_up(self):
        release = threading.Event()
        written = []

        def slow_patch(*a, **k):
            written.append(k["json"]["files"]["match_state.json"]["content"])
            release.wait(5)
            return _response()

        with patch.object(gist.net.SESSION, "patch", slow_patch):
            with gist.background():
                gist.salva_stato_su_gist({"v": 1})
                REAL_SLEEP(0.1)                       # il thread e' dentro la prima scrittura
                for v in (2, 3, 4):
                    gist.salva_stato_su_gist({"v": v})
            release.set()
            gist.flush(5)
        self.assertEqual(len(written), 2)
        self.assertIn('"v": 4', written[-1])

    def test_failure_is_reported_to_next_cycle(self):
        with patch.object(gist.net.SESSION, "patch", lambda *a, **k: _response(500)):
            with gist.background():
                gist.salva_stato_su_gist({"a": 1})
            gist.flush(5)
        self.assertTrue(gist.take_async_failure())
        self.assertFalse(gist.take_async_failure())

    def test_sync_save_still_blocks_and_marks_dirty_on_failure(self):
        state = {"a": 1}
        with patch.object(gist.net.SESSION, "patch", lambda *a, **k: _response(500)):
            self.assertFalse(gist.salva_stato_su_gist(state))
        self.assertTrue(state["_gist_dirty"])
        with patch.object(gist.net.SESSION, "patch", lambda *a, **k: _response()):
            self.assertTrue(gist.salva_stato_su_gist(state))
        self.assertNotIn("_gist_dirty", state)

    def test_sync_save_supersedes_queued_older_state(self):
        release = threading.Event()
        written = []

        def slow_patch(*a, **k):
            written.append(k["json"]["files"]["match_state.json"]["content"])
            if len(written) == 1:
                release.wait(5)
            return _response()

        with patch.object(gist.net.SESSION, "patch", slow_patch):
            with gist.background():
                gist.salva_stato_su_gist({"v": 1})
                REAL_SLEEP(0.1)
                gist.salva_stato_su_gist({"v": 2})        # in coda
            threading.Timer(0.2, release.set).start()
            gist.salva_stato_su_gist({"v": 3})            # sincrono: piu' recente
            gist.flush(5)
        self.assertIn('"v": 3', written[-1])
        self.assertNotIn('"v": 2', "".join(written))


if __name__ == "__main__":
    unittest.main()
