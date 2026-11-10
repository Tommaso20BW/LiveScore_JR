"""Ricerca della partita su ESPN (prima le leghe della squadra) e partite rinviate/annullate/sospese."""
import unittest
from unittest.mock import patch

from livescore.core import leagues
from livescore.espn import client, parser


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


def _board(name, event_id, team_ids):
    return {
        "leagues": [{"name": name}],
        "events": [{
            "id": event_id,
            "date": "2026-11-10T19:45Z",
            "competitions": [{"competitors": [{"team": {"id": t}} for t in team_ids]}],
        }],
    }


class _FakeSession:
    """Risponde per lega e registra le richieste, in ordine."""

    def __init__(self, boards, broken=(), refused=None):
        self.boards = boards
        self.broken = set(broken)
        self.refused = dict(refused or {})     # lega -> quante volte ESPN risponde 403
        self.calls = []

    def get(self, url, params=None, timeout=None):
        slug = url.rstrip("/").split("/")[-2]
        self.calls.append((slug, params["dates"]))
        if slug in self.broken:
            raise ConnectionError("rete")
        if self.refused.get(slug, 0) > 0:
            self.refused[slug] -= 1
            return _Response({}, status=403)
        if slug in self.boards:
            return _Response(self.boards[slug])
        return _Response({}, status=404)


class MatchSearchTest(unittest.TestCase):
    SLUGS = ["lega.0", "lega.1", "ita.1", "lega.3", "club.friendly", "fifa.friendly", "lega.6"]

    def _search(self, session, team_id="111"):
        with patch.object(client.net, "SESSION", session),                 patch.object(leagues, "LEAGUE_SLUGS", self.SLUGS),                 patch.object(client.time, "sleep", lambda _s: None):
            return client.trova_partita_oggi(team_id)

    def test_team_leagues_are_asked_first(self):
        session = _FakeSession({"ita.1": _board("Serie A", "E1", ["111", "9"])})
        found = self._search(session)
        self.assertEqual((found["event_id"], found["league_slug"], found["league_name"]), ("E1", "ita.1", "Serie A"))
        self.assertEqual(found["date"], "2026-11-10T19:45Z")
        self.assertEqual(len(found["competitors"]), 2)
        self.assertEqual([slug for slug, _date in session.calls], ["ita.1"])

    def test_national_team_uses_its_own_leagues(self):
        session = _FakeSession({"fifa.friendly": _board("Amichevoli", "E9", ["162", "9"])})
        self.assertEqual(self._search(session, team_id="162")["event_id"], "E9")
        self.assertEqual([slug for slug, _date in session.calls], ["fifa.friendly"])

    def test_other_leagues_keep_the_list_order(self):
        session = _FakeSession({
            "lega.6": _board("Sei", "E6", ["111", "9"]),
            "lega.1": _board("Uno", "E1", ["111", "7"]),
        })
        self.assertEqual(self._search(session)["event_id"], "E1")
        self.assertEqual([slug for slug, _date in session.calls], ["ita.1", "club.friendly", "lega.0", "lega.1"])

    def test_unknown_team_scans_the_list_as_before(self):
        session = _FakeSession({"lega.3": _board("Tre", "E3", ["999", "7"])})
        self.assertEqual(self._search(session, team_id="999")["event_id"], "E3")
        self.assertEqual([slug for slug, _date in session.calls], ["lega.0", "lega.1", "ita.1", "lega.3"])

    def test_errors_and_other_teams_are_skipped(self):
        session = _FakeSession(
            {"lega.1": _board("Uno", "E1", ["5", "6"]), "lega.6": _board("Sei", "E6", ["6", "111"])},
            broken={"lega.0", "lega.3"},
        )
        self.assertEqual(self._search(session)["event_id"], "E6")

    def test_refused_team_league_is_retried(self):
        session = _FakeSession({"ita.1": _board("Serie A", "E1", ["111", "9"])}, refused={"ita.1": 2})
        self.assertEqual(self._search(session)["event_id"], "E1")
        self.assertEqual([slug for slug, _date in session.calls], ["ita.1"] * 3)

    def test_refused_other_league_is_not_retried(self):
        session = _FakeSession({}, refused={"lega.0": 99})
        self.assertIsNone(self._search(session))
        self.assertEqual(session.calls.count(("lega.0", session.calls[0][1])), 1)

    def test_no_match_tries_both_days_once_per_league(self):
        session = _FakeSession({})
        self.assertIsNone(self._search(session))
        self.assertEqual(len(session.calls), 2 * len(self.SLUGS))
        self.assertEqual(len(set(session.calls)), 2 * len(self.SLUGS))

    def test_section_titles_are_not_leagues(self):
        self.assertTrue(leagues.LEAGUE_SLUGS)
        self.assertFalse([slug for slug in leagues.LEAGUE_SLUGS if slug.startswith("--")])
        self.assertIn("ita.1", leagues.LEAGUE_SLUGS)


def _event(name, state):
    return {"header": {"competitions": [{"status": {"type": {"name": name, "state": state}}}]}}


class CalledOffTest(unittest.TestCase):
    def test_called_off_states(self):
        cases = {
            ("STATUS_POSTPONED", "post"): "rinviata",
            ("STATUS_POSTPONED", "pre"): "rinviata",
            ("STATUS_CANCELED", "post"): "annullata",
            ("STATUS_CANCELLED", "pre"): "annullata",
            ("STATUS_ABANDONED", "post"): "sospesa definitivamente",
            ("STATUS_SUSPENDED", "post"): "sospesa",
            ("STATUS_FORFEIT", "post"): "decisa a tavolino",
        }
        for (name, state), label in cases.items():
            self.assertEqual(parser.match_called_off(_event(name, state)), label, name)

    def test_regular_matches_are_untouched(self):
        for name, state in (("STATUS_SCHEDULED", "pre"), ("STATUS_FIRST_HALF", "in"), ("STATUS_HALFTIME", "in"),
                            ("STATUS_FULL_TIME", "post"), ("STATUS_FINAL_PEN", "post"), ("STATUS_FINAL_AET", "post")):
            self.assertIsNone(parser.match_called_off(_event(name, state)), name)
        self.assertEqual(parser.parse_status(_event("STATUS_FULL_TIME", "post")), ("FT", 90))

    def test_suspension_in_play_keeps_following(self):
        # Sospesa ma evento ancora aperto: può riprendere, il bot resta in ascolto.
        self.assertIsNone(parser.match_called_off(_event("STATUS_SUSPENDED", "in")))
        self.assertIsNone(parser.match_called_off(_event("STATUS_ABANDONED", "in")))

    def test_broken_payload(self):
        self.assertIsNone(parser.match_called_off({}))


if __name__ == "__main__":
    unittest.main()
