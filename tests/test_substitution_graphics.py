"""Grafica CAMBIO (SUB / SUBS) solo per i cambi Juventus (mai amichevoli), foto rifatta a ogni correzione."""

import io
import unittest
from unittest.mock import patch

from PIL import Image

from livescore.graphics import goal as g
from livescore.graphics import substitution as sub_graphics
from livescore.hooks import bot
from livescore.match import substitutions as subs
from livescore.match.context import MatchContext
from tests.sim_scenarios import CONCEICAO, LAUTARO, LOCATELLI, MCKENNIE, THURAM, BARELLA, sub
from tests.sim_support import AWAY_ID, HOME_ID, Sim, payload


def entry(display, short, last, jersey):
    athlete = {"displayName": display, "shortName": short}
    if last:
        athlete["lastName"] = last
    return {"jersey": jersey, "athlete": athlete}


JUVE_ROSTER = [
    entry("Khephren Thuram", "K. Thuram", "Thuram", "19"),
    entry("Manuel Locatelli", "M. Locatelli", "Locatelli", "5"),
    entry("Francisco Conceicao", "F. Conceicao", "Conceicao", "7"),
    entry("Weston McKennie", "W. McKennie", "McKennie", "22"),
    entry("Douglas Luiz", "D. Luiz", "Luiz", "12"),
    entry("Bremer", "Bremer", None, "3"),
    entry("Randal Kolo Muani", "R. Kolo Muani", None, "9"),
]
INTER_ROSTER = [
    entry("Lautaro Martinez", "L. Martinez", "Martinez", "10"),
    entry("Nicolo Barella", "N. Barella", "Barella", "23"),
]
ROSTERS = [{"team": {"id": HOME_ID}, "roster": JUVE_ROSTER}, {"team": {"id": AWAY_ID}, "roster": INTER_ROSTER}]


def frame(*events, t=0, clock="60'", rosters=True):
    p = payload(clock=clock, period=2, key_events=list(events))
    if rosters:
        p["rosters"] = ROSTERS
    return t, p


def run(frames, end=700):
    sim = Sim(bot, frames, end, graphics=True)
    sim.run()
    return sim


def cambi(sim):
    """(metodo, id messaggio, testo o didascalia) dei messaggi CAMBIO riusciti."""
    rows = []
    for e in sim.telegram:
        body = e["body"]
        text = body.get("text") or body.get("caption") or body.get("media") or ""
        if e["ok"] and "CAMBIO" in text:
            rows.append((e["method"], e.get("message_id"), text))
    return rows


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.players = subs.roster_index({"rosters": ROSTERS}, HOME_ID)

    def test_numbers_and_surnames_from_espn_rosters(self):
        pairs = subs.graphic_pairs([{"in": "K. Thuram", "out": "M. Locatelli"},
                                    {"in": "Bremer", "out": "R. Kolo Muani"}], self.players)
        self.assertEqual(pairs, [(("5", "Locatelli", "Manuel Locatelli"), ("19", "Thuram", "Khephren Thuram")),
                                 (("9", "Kolo Muani", "Randal Kolo Muani"), ("3", "Bremer", "Bremer"))])

    def test_shirt_name_override(self):
        pairs = subs.graphic_pairs([{"in": "D. Luiz", "out": "W. McKennie"}], self.players)
        self.assertEqual(pairs[0][1], ("12", "Douglas Luiz", "Douglas Luiz"))

    def test_unknown_player_or_missing_number_means_no_graphic(self):
        self.assertIsNone(subs.graphic_pairs([{"in": "X. Nessuno", "out": "M. Locatelli"}], self.players))
        no_number = subs.roster_index({"rosters": [{"team": {"id": HOME_ID},
                                                    "roster": [entry("Manuel Locatelli", "M. Locatelli", "Locatelli", ""),
                                                               entry("Khephren Thuram", "K. Thuram", "Thuram", "19")]}]},
                                      HOME_ID)
        self.assertIsNone(subs.graphic_pairs([{"in": "K. Thuram", "out": "M. Locatelli"}], no_number))

    def test_only_juve_and_never_friendlies(self):
        ctx = MatchContext(home_id=HOME_ID, away_id=AWAY_ID, league_slug="ita.1", league_name="Serie A")
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True):
            self.assertTrue(subs.graphic_eligible(ctx, HOME_ID))
            self.assertFalse(subs.graphic_eligible(ctx, AWAY_ID))
            ctx.league_slug, ctx.league_name = "club.friendly", "Club Friendly"
            self.assertFalse(subs.graphic_eligible(ctx, HOME_ID))
        ctx.league_slug, ctx.league_name = "ita.1", "Serie A"
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", False):
            self.assertFalse(subs.graphic_eligible(ctx, HOME_ID))


class RenderTests(unittest.TestCase):
    def test_portrait_png_for_one_to_five_substitutions(self):
        pairs = [(("22", "McKennie", "Weston McKennie"), ("10", "Yildiz", "Kenan Yildiz")),
                 (("8", "Koopmeiners", "Teun Koopmeiners"), ("7", "Conceição", "Francisco Conceição")),
                 (("20", "Cambiaso", "Andrea Cambiaso"), ("40", "Radu", "Ionuț Radu")),
                 (("4", "Gatti"), ("24", "Rugani")),                      # senza nome completo: solo il cognome
                 (("14", "Milik", "Arkadiusz Milik"), ("9", "Kolo Muani", "Randal Kolo Muani"))]
        with patch.object(g, "_remote_espn_team_logo", return_value=None):
            for n in (1, 2, 3, 4, 5):
                for kit, comp in (("home", "ita.1"), ("away", "ita.1"), ("third", "uefa.champions"),
                                  ("home", "uefa.europa"), ("home", "coppa_italia")):
                    png = sub_graphics.render_png(pairs[:n], home_name="Juventus", away_name="Inter",
                                                  home_id=HOME_ID, away_id=AWAY_ID, kit=kit, competition=comp)
                    self.assertEqual(Image.open(io.BytesIO(png)).size, (1086, 1448))

    def test_missing_number_raises(self):
        with self.assertRaises(sub_graphics.SubstitutionGraphicUnavailable):
            sub_graphics.render([(("", "Locatelli"), ("19", "Thuram"))], home_name="Juventus", away_name="Inter",
                                home_id=HOME_ID, away_id=AWAY_ID)

    def test_letters_missing_from_font_lose_the_accent(self):
        font = str(g.DEFAULT_ASSET_DIR / sub_graphics.NAME_FONT)
        self.assertEqual(sub_graphics.printable("Conceição", font), "CONCEIÇÃO")
        self.assertEqual(sub_graphics.printable("  kolo   muani ", font), "KOLO MUANI")


@patch.object(sub_graphics, "render_png", return_value=b"png")
class TelegramFlowTests(unittest.TestCase):
    def test_juve_substitution_is_a_photo_with_the_usual_caption(self, render):
        sim = run([frame(sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI))])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendPhoto"])
        self.assertIn("CAMBIO JUVENTUS · 60'", rows[0][2])
        pairs = render.call_args.args[0]
        self.assertEqual(pairs, [(("5", "Locatelli", "Manuel Locatelli"), ("19", "Thuram", "Khephren Thuram"))])
        self.assertEqual(render.call_args.kwargs["competition"], "ita.1")

    def test_correction_replaces_the_photo_in_the_same_message(self, render):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "60'", 2, HOME_ID, CONCEICAO, LOCATELLI)     # ESPN corregge chi entra
        sim = run([frame(s1, t=0), frame(s1_fixed, t=120, clock="63'")])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendPhoto", "editMessageMedia"])
        self.assertEqual(rows[0][1], rows[1][1], "la correzione deve cambiare la foto dello stesso messaggio")
        self.assertIn("F. Conceicao", rows[1][2])
        self.assertEqual(render.call_args.args[0], [(("5", "Locatelli", "Manuel Locatelli"),
                                                     ("7", "Conceicao", "Francisco Conceicao"))])

    def test_added_substitution_redraws_with_both(self, render):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s2 = sub("s2", "61'", 2, HOME_ID, CONCEICAO, MCKENNIE)
        sim = run([frame(s1, t=0), frame(s1, s2, t=120, clock="62'")])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendPhoto", "editMessageMedia"])
        self.assertEqual(len(render.call_args.args[0]), 2)

    def test_opponent_substitution_stays_text(self, render):
        sim = run([frame(sub("s1", "60'", 2, AWAY_ID, LAUTARO, BARELLA))])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendMessage"])
        render.assert_not_called()

    def test_without_shirt_numbers_text_then_photo_on_next_correction(self, render):
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "61'", 2, HOME_ID, THURAM, LOCATELLI)
        sim = run([frame(s1, t=0, rosters=False), frame(s1_fixed, t=120, clock="63'")])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendMessage", "editMessageMedia"])
        self.assertEqual(rows[0][1], rows[1][1])

    def test_photo_that_cannot_be_redrawn_becomes_correct_text(self, render):
        render.side_effect = [b"png", RuntimeError("render")]
        s1 = sub("s1", "60'", 2, HOME_ID, THURAM, LOCATELLI)
        s1_fixed = sub("s1", "62'", 2, HOME_ID, THURAM, LOCATELLI)
        sim = run([frame(s1, t=0), frame(s1_fixed, t=120, clock="63'")])
        rows = cambi(sim)
        self.assertEqual([r[0] for r in rows], ["sendPhoto", "sendMessage"])
        deleted = [e for e in sim.telegram if e["method"] == "deleteMessage"]
        self.assertEqual([e["body"]["message_id"] for e in deleted], [rows[0][1]], "niente foto sbagliata")


if __name__ == "__main__":
    unittest.main()
