import io
import os
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

import dynamic_kit_runtime as dkr
import canva_snapshot_store as css


def png(color):
    image = Image.new("RGBA", (3, 3), color)
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {"ok": True, "result": {}}
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeBot:
    JUVE_ID = "111"
    BOT_TOKEN = "token"
    CHAT_ID = "-100-live"
    BOT_JR_CHAT_ID = "-100-botjr"
    GOAL_GRAPHICS_ENABLED = True
    GH_PAT = "token"
    GITHUB_REPOSITORY = "owner/repo"
    SESSION = None
    MOMENTI_CONFIG = {
        "HT": {"titolo": "<b>STATS PRIMO TEMPO</b>"},
        "2H_END": {"titolo": "<b>STATS SECONDO TEMPO</b>"},
        "FT": {"titolo": "<b>STATS FINE PARTITA</b>"},
    }

    def __init__(self):
        self.saved = []
        self.posts = []
        self.updates = []
        self.goal_graphics = SimpleNamespace()
        self.log_line = Mock()

    def parse_score(self, competitors):
        home = next(x for x in competitors if x["homeAway"] == "home")
        away = next(x for x in competitors if x["homeAway"] == "away")
        return (
            str(home["team"]["id"]),
            str(away["team"]["id"]),
            home["team"]["displayName"],
            away["team"]["displayName"],
            int(home.get("score", 0)),
            int(away.get("score", 0)),
        )

    def determina_kit(self, home_id, away_id, league_slug="", league_name=""):
        return "home" if str(home_id) == "111" else "away"

    def is_friendly_competition(self, slug, name=""):
        return False

    def _tg_post(self, method, payload=None, data=None, files=None, timeout=10):
        self.posts.append((method, payload, data, files))
        if method == "getUpdates":
            result = list(self.updates)
            self.updates = []
            return FakeResponse({"ok": True, "result": result})
        return FakeResponse()

    def _save(self, state):
        self.saved.append(json.loads(json.dumps(state)))


def match():
    competitors = [
        {
            "homeAway": "home",
            "team": {"id": "111", "displayName": "Juventus"},
            "score": "0",
        },
        {
            "homeAway": "away",
            "team": {"id": "147", "displayName": "NEC Nijmegen"},
            "score": "0",
        },
    ]
    return {
        "event_id": "123",
        "league_slug": "ita.1",
        "league_name": "Serie A",
        "competitors": competitors,
        "competition": {"competitors": competitors},
    }


def summary(kit=None):
    uniform = {} if kit is None else {"type": kit}
    return {
        "header": {
            "competitions": [{
                "competitors": match()["competitors"],
            }]
        },
        "boxscore": {
            "teams": [
                {
                    "homeAway": "home",
                    "team": {
                        "id": "111",
                        "uniform": uniform,
                    },
                },
                {
                    "homeAway": "away",
                    "team": {
                        "id": "147",
                        "uniform": {"type": "away"},
                    },
                },
            ]
        },
    }


class DynamicKitPureTests(unittest.TestCase):
    def test_uniform_missing_and_valid_values(self):
        self.assertIsNone(dkr.extract_juventus_uniform(summary(None)))
        self.assertEqual(dkr.extract_juventus_uniform(summary("third")), "third")
        self.assertEqual(dkr.extract_juventus_uniform(summary("home")), "home")

    def test_keyboard_marks_auto_or_manual(self):
        auto = dkr.keyboard_for("123", "auto", "third")
        labels = [button["text"] for button in auto["inline_keyboard"][0]]
        self.assertEqual(labels[-1], "✅ AUTO")
        manual = dkr.keyboard_for("123", "manual", "third")
        labels = [button["text"] for button in manual["inline_keyboard"][0]]
        self.assertEqual(labels[2], "✅ THIRD")

    def test_callback_data_is_event_scoped(self):
        self.assertEqual(
            dkr.parse_callback_data("kit:401874750:home"),
            ("401874750", "home"),
        )
        self.assertEqual(dkr.parse_callback_data("other:1:home"), (None, None))


class SnapshotArchiveTests(unittest.TestCase):
    def test_snapshot_zip_is_deterministic_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            for name in css.REQUIRED_FILES:
                (source / name).write_bytes((name + "-content").encode())

            first = css._deterministic_zip(source)
            second = css._deterministic_zip(source)
            self.assertEqual(first, second)

            restored = Path(tmp) / "restored"
            css._extract_snapshot_zip(first, restored)
            for name in css.REQUIRED_FILES:
                self.assertEqual(
                    (restored / name).read_bytes(),
                    (source / name).read_bytes(),
                )

    def test_invalid_snapshot_archive_is_rejected(self):
        stream = io.BytesIO()
        import zipfile
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("source.pdf", b"x")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                css._extract_snapshot_zip(
                    stream.getvalue(),
                    Path(tmp),
                )


class DynamicKitRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.bot = FakeBot()
        self.runtime = dkr.DynamicKitRuntime(self.bot)

        # Install only the original state-save hooks needed by these direct tests.
        self.runtime._originals["salva_stato_su_gist"] = self.bot._save
        self.runtime._originals["stats_build_html"] = Mock()
        self.runtime._originals["render_goal"] = Mock()
        self.runtime._originals["render_saved"] = Mock()

        self.runtime.prepare_match(match(), summary(None))
        self.state = {
            "event_id": "123",
            "sent_periods": [],
        }
        self.runtime.state_ref = self.state
        self.runtime._sync_to_state(self.state)

    def test_missing_uniform_uses_fallback(self):
        self.assertEqual(self.runtime.active_kit, "home")
        self.assertIsNone(self.runtime.espn_kit)

    def test_auto_follows_espn_and_keeps_last_valid_if_field_disappears(self):
        self.runtime.observe_summary(summary("third"))
        self.assertEqual(self.runtime.espn_kit, "third")
        self.assertEqual(self.runtime.active_kit, "third")

        self.runtime.observe_summary(summary(None))
        self.assertEqual(self.runtime.espn_kit, "third")
        self.assertEqual(self.runtime.active_kit, "third")

    def test_manual_records_espn_but_does_not_override(self):
        self.runtime.kit_mode = "manual"
        self.runtime.manual_kit = "away"
        self.runtime.active_kit = "away"

        self.runtime.observe_summary(summary("third"))

        self.assertEqual(self.runtime.espn_kit, "third")
        self.assertEqual(self.runtime.active_kit, "away")

    def test_old_state_gets_backward_compatible_defaults(self):
        old = {"event_id": "123", "goals_detected": 1}
        self.runtime._hydrate_from_state(old)
        for key in (
            "kit_mode",
            "manual_kit",
            "espn_kit",
            "active_kit",
            "kit_fallback",
            "kit_media",
            "kit_update_offset",
            "kit_processed_callbacks",
            "kit_recap_message_id",
        ):
            self.assertIn(key, old)

    def test_visual_identical_media_is_not_edited(self):
        old = png((10, 20, 30, 255))
        self.runtime.active_kit = "third"
        self.runtime.volatile_media = {
            "55": {
                "message_id": 55,
                "chat_id": "-100-live",
                "type": "goal",
                "caption": "goal",
                "kit": "home",
                "visual_hash": dkr._pixel_hash(old),
                "render": {},
            }
        }
        self.runtime._render_record = Mock(return_value=old)
        self.runtime._edit_media_record = Mock(return_value=True)

        edited, same, failed = self.runtime.refresh_all_media()

        self.assertEqual((edited, same, failed), (0, 1, 0))
        self.runtime._edit_media_record.assert_not_called()
        self.assertEqual(self.runtime.volatile_media["55"]["kit"], "third")

    def test_changed_media_edits_same_message(self):
        old = png((10, 20, 30, 255))
        new = png((40, 50, 60, 255))
        self.runtime.active_kit = "away"
        self.runtime.volatile_media = {
            "55": {
                "message_id": 55,
                "chat_id": "-100-live",
                "type": "goal",
                "caption": "goal",
                "kit": "home",
                "visual_hash": dkr._pixel_hash(old),
                "render": {},
            }
        }
        self.runtime._render_record = Mock(return_value=new)
        self.runtime._edit_media_record = Mock(return_value=True)

        edited, same, failed = self.runtime.refresh_all_media()

        self.assertEqual((edited, same, failed), (1, 0, 0))
        record = self.runtime.volatile_media["55"]
        self.assertEqual(record["message_id"], 55)
        self.assertEqual(record["kit"], "away")

    def test_phase_regeneration_requires_original_canva_snapshot(self):
        self.runtime.portrait_graphics = SimpleNamespace(phase=Mock(return_value=b"png"))
        self.runtime.active_kit = "third"

        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp)
            for name in ("source.pdf", "background.png", "player.png", "manifest.json"):
                (snap / name).write_bytes(b"x")

            record = {
                "type": "half",
                "canva_snapshot": str(snap),
                "render": {
                    "kind": "half",
                    "home_name": "Juventus",
                    "away_name": "NEC Nijmegen",
                    "home_id": "111",
                    "away_id": "147",
                    "home_goals": 1,
                    "away_goals": 0,
                    "league_slug": "ita.1",
                },
            }

            self.runtime._render_record(record, "third")
            kwargs = self.runtime.portrait_graphics.phase.call_args.kwargs
            self.assertEqual(kwargs["layers"], snap)
            self.assertEqual(kwargs["kit"], "third")

    def test_missing_snapshot_does_not_silently_download_new_canva(self):
        record = {
            "type": "half",
            "canva_snapshot": "/definitely/missing/snapshot",
            "render": {"kind": "half"},
        }
        with self.assertRaises(FileNotFoundError):
            self.runtime._render_record(record, "third")

    def test_finish_match_removes_buttons_and_cleans_cache(self):
        self.runtime.recap_message_id = 99
        self.runtime.recap_chat_id = "-100-botjr"
        self.runtime.snapshot_store = Mock()

        with tempfile.TemporaryDirectory() as tmp:
            old = Path.cwd()
            try:
                os.chdir(tmp)
                cache = Path("canva_page1_cache")
                cache.mkdir()
                (cache / "source.pdf").write_bytes(b"pdf")
                self.runtime.finish_match()
                self.assertFalse(cache.exists())
            finally:
                os.chdir(old)

        methods = [item[0] for item in self.bot.posts]
        self.assertIn("editMessageReplyMarkup", methods)

    def _queue_callback(self, update_id, callback_id, data):
        self.bot.updates = [{
            "update_id": update_id,
            "callback_query": {
                "id": callback_id,
                "data": data,
                "message": {
                    "chat": {"id": "-100-botjr"},
                },
            },
        }]
        self.runtime.recap_chat_id = "-100-botjr"

    def test_manual_callback_switches_kit_and_auto_removes_override(self):
        self.runtime.espn_kit = "third"
        self.runtime.active_kit = "third"
        self.runtime.refresh_all_media = Mock(return_value=(0, 0, 0))
        self.runtime._edit_recap = Mock()

        self._queue_callback(10, "cb-home", "kit:123:home")
        self.runtime.poll_callbacks()
        self.assertEqual(self.runtime.kit_mode, "manual")
        self.assertEqual(self.runtime.manual_kit, "home")
        self.assertEqual(self.runtime.active_kit, "home")

        self._queue_callback(11, "cb-auto", "kit:123:auto")
        self.runtime.poll_callbacks()
        self.assertEqual(self.runtime.kit_mode, "auto")
        self.assertIsNone(self.runtime.manual_kit)
        self.assertEqual(self.runtime.active_kit, "third")

    def test_callback_for_other_event_is_ignored(self):
        self.runtime.active_kit = "home"
        self.runtime.refresh_all_media = Mock()
        self._queue_callback(20, "cb-other", "kit:999:third")

        self.runtime.poll_callbacks()

        self.assertEqual(self.runtime.active_kit, "home")
        self.runtime.refresh_all_media.assert_not_called()

    def test_duplicate_callback_is_ignored(self):
        self.runtime.active_kit = "home"
        self.runtime.processed_callback_ids = ["cb-dup"]
        self.runtime.refresh_all_media = Mock()
        self._queue_callback(21, "cb-dup", "kit:123:third")

        self.runtime.poll_callbacks()

        self.assertEqual(self.runtime.active_kit, "home")
        self.runtime.refresh_all_media.assert_not_called()

    def test_fetch_wrapper_does_not_add_an_extra_espn_request(self):
        fetch = Mock(return_value=summary("third"))
        self.runtime._originals["fetch_evento"] = fetch
        self.runtime.observe_summary = Mock()
        self.runtime.poll_callbacks = Mock()

        result = self.runtime._fetch_evento_proxy("123", "ita.1")

        self.assertIs(result, fetch.return_value)
        fetch.assert_called_once_with("123", "ita.1")
        self.runtime.observe_summary.assert_called_once_with(fetch.return_value)
        self.runtime.poll_callbacks.assert_called_once_with()

    def test_phase_missing_local_snapshot_is_restored_from_remote(self):
        self.runtime.portrait_graphics = SimpleNamespace(
            phase=Mock(return_value=b"png")
        )
        self.runtime.active_kit = "third"

        with tempfile.TemporaryDirectory() as tmp:
            restored = Path(tmp) / "restored"
            restored.mkdir()
            for name in css.REQUIRED_FILES:
                (restored / name).write_bytes(b"x")

            store = Mock()
            store.restore_snapshot.return_value = restored
            self.runtime.snapshot_store = store

            record = {
                "type": "half",
                "canva_snapshot": "/missing/runner/path",
                "canva_snapshot_remote": {
                    "branch": "runtime-snapshots",
                    "path": "runtime_snapshots/123/half_abc.zip",
                    "sha256": "abc",
                },
                "render": {
                    "kind": "half",
                    "home_name": "Juventus",
                    "away_name": "NEC Nijmegen",
                    "home_id": "111",
                    "away_id": "147",
                    "home_goals": 1,
                    "away_goals": 0,
                    "league_slug": "ita.1",
                },
            }

            self.runtime._render_record(record, "third")

            store.restore_snapshot.assert_called_once()
            self.assertEqual(
                record["canva_snapshot"],
                str(restored),
            )
            kwargs = self.runtime.portrait_graphics.phase.call_args.kwargs
            self.assertEqual(kwargs["layers"], restored)

    def test_finish_match_cleans_remote_event_folder(self):
        self.runtime.recap_message_id = 99
        self.runtime.recap_chat_id = "-100-botjr"
        store = Mock()
        self.runtime.snapshot_store = store

        with tempfile.TemporaryDirectory() as tmp:
            old = Path.cwd()
            try:
                os.chdir(tmp)
                self.runtime.finish_match()
            finally:
                os.chdir(old)

        store.cleanup_event.assert_called_once_with("123")

    def test_registry_is_persisted_in_match_state(self):
        self.runtime.volatile_media = {
            "77": {
                "message_id": 77,
                "type": "saved",
                "caption": "saved",
                "kit": "home",
                "render": {"goalkeeper_name": "Guglielmo Vicario"},
            }
        }
        self.runtime._sync_to_state(self.state)
        self.assertEqual(
            self.state["kit_media"]["77"]["message_id"],
            77,
        )


if __name__ == "__main__":
    unittest.main()
