"""Italia: pulsanti HOME/AWAY/AUTO del Bot JR, come per la Juventus (temi ita_home / ita_away)."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from livescore.kits import runtime as dkr
from livescore.match import teams
from tests.test_dynamic_kit_runtime import FakeBot, png


def italy_match(italy_home=True):
    italy = {"team": {"id": "162", "displayName": "Italy"}, "score": "0"}
    other = {"team": {"id": "478", "displayName": "France"}, "score": "0"}
    home, away = (italy, other) if italy_home else (other, italy)
    competitors = [{**home, "homeAway": "home"}, {**away, "homeAway": "away"}]
    return {"event_id": "555", "league_slug": "uefa.nations", "league_name": "UEFA Nations League",
            "competitors": competitors, "competition": {"competitors": competitors}}


def italy_summary(color=None, italy_home=True):
    uniform = {} if color is None else {"color": color}
    return {"header": {"competitions": [{"competitors": italy_match(italy_home)["competitors"]}]},
            "boxscore": {"teams": [{"team": {"id": "162", "uniform": uniform}},
                                   {"team": {"id": "478", "uniform": {"color": "1b2a5b"}}}]}}


class ItalyKitRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.bot = FakeBot()
        self.runtime = dkr.DynamicKitRuntime(self.bot)
        self.runtime._originals["salva_stato_su_gist"] = self.bot._save
        self.runtime._originals["italy_kit"] = teams.italy_kit
        self.runtime._originals["render_goal"] = Mock(return_value=SimpleNamespace(png=png((1, 1, 1, 255))))
        self.runtime._originals["stats_build_html"] = Mock(return_value="<html>")
        self.runtime.portrait_graphics = SimpleNamespace(phase=Mock(return_value=png((2, 2, 2, 255))))

    def _prepare(self, color=None, italy_home=True):
        self.runtime.prepare_match(italy_match(italy_home), italy_summary(color, italy_home))
        self.runtime.state_ref = {"event_id": "555"}
        self.runtime._sync_to_state(self.runtime.state_ref)

    def _click(self, update_id, choice):
        self.bot.updates = [{"update_id": update_id, "callback_query": {
            "id": f"cb-{update_id}", "data": f"kit:555:{choice}", "message": {"chat": {"id": "-100-botjr"}}}}]
        self.runtime.recap_chat_id = "-100-botjr"
        self.runtime.poll_callbacks()

    def test_italy_match_gets_home_away_auto_buttons(self):
        self._prepare()
        self.assertTrue(self.runtime.enabled)
        buttons = [b["callback_data"] for b in self.runtime.keyboard_for_current()["inline_keyboard"][0]]
        self.assertEqual(buttons, ["kit:555:home", "kit:555:away", "kit:555:auto"])

    def test_juventus_keyboard_is_unchanged(self):
        buttons = [b["text"] for b in dkr.keyboard_for("1", "auto", "home")["inline_keyboard"][0]]
        self.assertEqual(buttons, ["HOME", "AWAY", "THIRD", "✅ AUTO"])

    def test_auto_follows_the_shirt_colour_then_the_side(self):
        self._prepare(color="ffffff")                         # Italia in casa ma in bianco
        self.assertEqual(self.runtime._italy_kit_proxy({}, "162"), "ita_away")
        self._prepare(color=None, italy_home=False)           # ESPN non dice nulla: fuori casa
        self.assertEqual(self.runtime._italy_kit_proxy({}, "478"), "ita_away")
        self._prepare(color=None, italy_home=True)
        self.assertEqual(self.runtime._italy_kit_proxy({}, "162"), "ita_home")

    def test_manual_choice_wins_and_auto_restores_espn(self):
        self._prepare(color="0b4dbb")                         # azzurra secondo ESPN
        self.runtime._schedule_refresh = Mock()
        self.runtime._edit_recap = Mock()
        self._click(1, "away")
        self.assertEqual((self.runtime.kit_mode, self.runtime.active_kit), ("manual", "away"))
        self.assertEqual(teams.graphics_kit({}, "162", "478", "Italy", "France"), "ita_home")  # senza runtime
        self.assertEqual(self.runtime._italy_kit_proxy({}, "162"), "ita_away")
        self.runtime._schedule_refresh.assert_called_once()
        self._click(2, "auto")
        self.assertEqual((self.runtime.kit_mode, self.runtime.active_kit), ("auto", "home"))

    def test_third_is_refused_for_italy(self):
        self._prepare()
        self.runtime._schedule_refresh = Mock()
        self._click(3, "third")
        self.assertEqual(self.runtime.active_kit, "home")
        self.runtime._schedule_refresh.assert_not_called()

    def test_phase_without_photo_is_registered_and_redrawn(self):
        self._prepare()

        def build(**kwargs):
            self.assertEqual(self.runtime._italy_kit_proxy({}, "162"), "ita_home")
            return png((3, 3, 3, 255))

        self.runtime._originals["build_phase_graphic"] = build
        out = self.runtime._build_phase_graphic_proxy(kind="full", home_id="162", away_id="478",
                                                      home_goals=2, away_goals=1)
        self.assertIsNotNone(out)                             # niente snapshot foto richiesto
        record = self.runtime.pending_render["full"]
        self.assertEqual(record["kit"], "home")
        self.assertIsNone(record["photo_snapshot"])

        self.runtime._render_record(record, "away")
        kwargs = self.runtime.portrait_graphics.phase.call_args.kwargs
        self.assertEqual((kwargs["kit"], kwargs["layers"], kwargs["home_goals"]), ("ita_away", None, 2))

    def test_goal_and_stats_are_redrawn_with_italy_themes(self):
        self._prepare()
        context = self.runtime._goal_context({"kit": "ita_home", "scorer_name": "Retegui"},
                                             SimpleNamespace(pose=None), "goal")
        self.assertEqual(context["render"]["kit"], "home")
        self.runtime._render_record(context, "away")
        self.assertEqual(self.runtime._originals["render_goal"].call_args.kwargs["kit"], "ita_away")

        self.runtime.stats_graphics = SimpleNamespace(render=Mock(side_effect=OSError("stop")))
        with self.assertRaises(OSError):
            self.runtime._render_record({"type": "stats", "render": {"kit": "home", "rows": []}}, "away")
        self.assertEqual(self.runtime._originals["stats_build_html"].call_args.kwargs["kit"], "ita_away")

    def test_juventus_match_is_not_treated_as_italy(self):
        from tests.test_dynamic_kit_runtime import match, summary
        self.runtime.prepare_match(match(), summary("third"))
        self.assertFalse(self.runtime.italy)
        self.assertEqual(self.runtime.active_kit, "third")


class ItalyUniformTests(unittest.TestCase):
    def test_uniform_and_fallback(self):
        self.assertEqual(teams.italy_uniform(italy_summary("ffffff")), "ita_away")
        self.assertEqual(teams.italy_uniform(italy_summary("1550a8")), "ita_home")
        self.assertIsNone(teams.italy_uniform(italy_summary(None)))
        self.assertEqual(teams.italy_kit(italy_summary(None), "162"), "ita_home")
        self.assertEqual(teams.italy_kit(italy_summary(None, False), "478"), "ita_away")


if __name__ == "__main__":
    unittest.main()
