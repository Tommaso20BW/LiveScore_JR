import re
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from livescore import scheduler

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def event(team_ids, kickoff, completed=False):
    return {
        "name": "A vs B",
        "date": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": {"type": {"completed": completed, "state": "post" if completed else "pre"}},
        "competitions": [{"competitors": [{"team": {"id": t}} for t in team_ids]}],
    }


class SchedulerTeamTests(unittest.TestCase):
    def test_contains_team(self):
        ev = event(["162", "5"], NOW)
        self.assertTrue(scheduler.contains_team(ev, "162"))
        self.assertFalse(scheduler.contains_team(ev, "111"))

    def test_italy_match_in_window_dispatches_with_italy_label(self):
        ko = NOW + timedelta(minutes=30)
        matches = {"162": (ko, event(["162", "5"], ko), "fifa.friendly")}
        team, *_ = scheduler.choose_match(matches, NOW)
        self.assertEqual(team["id"], "162")
        self.assertEqual(team["label"], "Italia")

    def test_juve_has_priority_when_both_in_window(self):
        ko = NOW + timedelta(minutes=30)
        matches = {
            "162": (ko, event(["162", "5"], ko), "uefa.nations"),
            "111": (ko, event(["111", "7"], ko), "ita.1"),
        }
        team, *_ = scheduler.choose_match(matches, NOW)
        self.assertEqual(team["id"], "111")

    def test_italy_used_when_juve_outside_window(self):
        far = NOW + timedelta(hours=20)
        ko = NOW + timedelta(minutes=30)
        matches = {
            "111": (far, event(["111", "7"], far), "ita.1"),
            "162": (ko, event(["162", "5"], ko), "uefa.nations"),
        }
        team, *_ = scheduler.choose_match(matches, NOW)
        self.assertEqual(team["id"], "162")

    def test_finished_match_not_dispatched(self):
        ko = NOW - timedelta(minutes=100)
        ok, _, finished = scheduler.evaluate_match(ko, event(["162"], ko, completed=True), NOW)
        self.assertFalse(ok)
        self.assertTrue(finished)

    def test_no_matches(self):
        self.assertIsNone(scheduler.choose_match({}, NOW))

    def test_scheduler_label_is_a_valid_workflow_option(self):
        workflow = (ROOT / ".github/workflows/main_espn.yml").read_text(encoding="utf-8")
        for team in scheduler.MONITORED_TEAMS:
            self.assertIn(f"'{team['label']}'", workflow)

    def test_graphics_checkbox_removed_and_always_enabled(self):
        workflow = (ROOT / ".github/workflows/main_espn.yml").read_text(encoding="utf-8")
        self.assertNotIn("inputs.goal_graphics", workflow)
        self.assertIn("GOAL_GRAPHICS_ENABLED: 'true'", workflow)
        self.assertIn("custom_team_id", workflow)



class EarlyLineupTests(unittest.TestCase):
    """Italia: formazione uscita prima dei 60 minuti -> il live parte subito per inviarla."""

    def setUp(self):
        from unittest import mock
        self.italy = scheduler.MONITORED_TEAMS[1]
        self.juve = scheduler.MONITORED_TEAMS[0]
        self.ev = dict(event(["162", "5"], NOW), id="777")
        patches = {
            "lineup_published": mock.patch.object(scheduler, "lineup_published", return_value=True),
            "lineup_already_sent": mock.patch.object(scheduler, "lineup_already_sent", return_value=False),
        }
        self.mocks = {name: p.start() for name, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

    def early(self, team, minutes, finished=False):
        return scheduler.early_lineup_dispatch(team, minutes, self.ev, "fifa.friendly", finished)

    def test_italy_lineup_out_dispatches(self):
        self.assertTrue(self.early(self.italy, 95))

    def test_not_for_juve_or_outside_window(self):
        self.assertFalse(self.early(self.juve, 95))
        self.assertFalse(self.early(self.italy, 45))
        self.assertFalse(self.early(self.italy, scheduler.LINEUP_WINDOW_MIN + 5))
        self.assertFalse(self.early(self.italy, 95, finished=True))

    def test_no_lineup_or_already_sent(self):
        self.mocks["lineup_published"].return_value = False
        self.assertFalse(self.early(self.italy, 95))
        self.mocks["lineup_published"].return_value = True
        self.mocks["lineup_already_sent"].return_value = True
        self.assertFalse(self.early(self.italy, 95))



class LineupHelpersTests(unittest.TestCase):
    def test_lineup_published_needs_eleven_italy_starters(self):
        from unittest import mock
        roster = {"rosters": [
            {"team": {"id": "5"}, "roster": [{"starter": True}] * 11},
            {"team": {"id": "162"}, "roster": [{"starter": True}] * 11 + [{"starter": False}] * 9},
        ]}
        with mock.patch.object(scheduler, "fetch_json", return_value=roster):
            self.assertTrue(scheduler.lineup_published("fifa.friendly", "777"))
        roster["rosters"][1]["roster"] = []
        with mock.patch.object(scheduler, "fetch_json", return_value=roster):
            self.assertFalse(scheduler.lineup_published("fifa.friendly", "777"))

    def test_already_sent_reads_live_state(self):
        from unittest import mock
        import json
        state = {"event_id": "777", "lineup": {"message_id": 5}}
        resp = mock.Mock(**{"json.return_value": {"files": {"match_state.json": {"content": json.dumps(state)}}}})
        with mock.patch.dict("os.environ", {"GH_PAT": "x", "GIST_ID": "y"}), \
                mock.patch.object(scheduler.SESSION, "get", return_value=resp):
            self.assertTrue(scheduler.lineup_already_sent("777"))
            self.assertFalse(scheduler.lineup_already_sent("888"))


if __name__ == "__main__":
    unittest.main()
