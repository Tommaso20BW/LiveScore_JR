"""Cancellazione delle copie su Bot JR, foto preparata in anticipo e letture ESPN veloci."""
import tempfile
import threading
import unittest
import zipfile
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from livescore.espn import client
from livescore.match import phase_photo
from livescore.state import snapshot_store


def desk():
    return phase_photo.Desk(token="t", chat_id="1", webapp_url="https://x", bot_chat_id="99", http=Mock())


class CopyDeleteTests(unittest.TestCase):
    def test_retries_after_temporary_error(self):
        d = desk()
        d._call = Mock(side_effect=[RuntimeError("Too Many Requests: retry after 2"), True])
        with patch.object(phase_photo.time, "sleep") as sleep:
            self.assertTrue(d._delete_copy(7))
        sleep.assert_called_once_with(2)
        self.assertEqual(d._call.call_count, 2)

    def test_already_deleted_is_fine(self):
        d = desk()
        d._call = Mock(side_effect=RuntimeError("Bad Request: message to delete not found"))
        self.assertTrue(d._delete_copy(7))
        self.assertEqual(d._call.call_count, 1)

    def test_failure_is_visible(self):
        d = desk()
        d._call = Mock(side_effect=RuntimeError("Forbidden"))
        with patch.object(phase_photo.time, "sleep"), patch.object(phase_photo, "log_line") as log:
            self.assertFalse(d._delete_copy(7))
        self.assertEqual(d._call.call_count, 3)
        self.assertEqual(log.call_args.args[0], "WARN")

    def test_finish_deletes_every_copy(self):
        d = desk()
        d.slots["half"]["copy_id"], d.slots["end"]["copy_id"] = 11, 12
        d._call = Mock(return_value=True)
        d.finish()
        ids = [c.args[1]["message_id"] for c in d._call.call_args_list]
        self.assertEqual(ids, [11, 12])


class PreloadTests(unittest.TestCase):
    def run_tick(self, d, status, minute):
        done = threading.Event()
        calls = []

        def hook(kind, path):
            calls.append((kind, path.name))
            done.set()

        with patch.object(phase_photo, "SNAPSHOT_PRELOAD", hook):
            d._preload_snapshots(SimpleNamespace(status=status, elapsed=minute))
            done.wait(0.3)
        return calls

    def test_only_from_minute_and_once(self):
        d = desk()
        d.slots["half"]["confirmed"] = {"layers": "foto1"}
        self.assertEqual(self.run_tick(d, "1H", 44), [])
        self.assertEqual(self.run_tick(d, "1H", 45), [("half", "foto1")])
        self.assertEqual(self.run_tick(d, "1H", 46), [])
        d.slots["half"]["confirmed"] = {"layers": "foto2"}      # foto cambiata
        self.assertEqual(self.run_tick(d, "1H", 46), [("half", "foto2")])


class SnapshotZipTests(unittest.TestCase):
    def test_png_not_recompressed_and_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in snapshot_store.REQUIRED_FILES:
                (folder / name).write_bytes(b"dati " + name.encode())
            first = snapshot_store._deterministic_zip(folder)
            self.assertEqual(first, snapshot_store._deterministic_zip(folder))
            with zipfile.ZipFile(io.BytesIO(first)) as archive:
                self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in archive.infolist()))


class EspnReadTests(unittest.TestCase):
    def test_slow_read_gets_second_chance(self):
        ok = Mock(status_code=200)
        ok.json.return_value = {"a": 1}
        with patch.object(client.net.LIVE_SESSION, "get", side_effect=[requests.Timeout("x"), ok]) as get:
            self.assertEqual(client.fetch_evento("1", "ita.1"), {"a": 1})
        self.assertEqual([c.kwargs["timeout"] for c in get.call_args_list], [(3, 5), (3, 12)])

    def test_gives_up_after_two(self):
        with patch.object(client.net.LIVE_SESSION, "get", side_effect=requests.ConnectionError("x")) as get:
            self.assertIsNone(client.fetch_evento("1", "ita.1"))
        self.assertEqual(get.call_count, 2)

    def test_error_status_is_not_retried_here(self):
        with patch.object(client.net.LIVE_SESSION, "get", return_value=Mock(status_code=429)) as get:
            self.assertIsNone(client.fetch_evento("1", "ita.1"))
        self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
