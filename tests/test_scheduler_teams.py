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


if __name__ == "__main__":
    unittest.main()
