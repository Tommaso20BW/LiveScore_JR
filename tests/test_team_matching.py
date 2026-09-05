import json
import unittest
from unittest.mock import Mock

import requests

from fclogo_sync import SyncReport, enrich_espn_teams, fetch_espn_teams
from team_matching import TeamIndex


def team(name, team_id, **extra):
    return {"name": name, "espn_id": str(team_id), **extra}


class TeamMatchingTests(unittest.TestCase):
    def test_exact_normalized_generic_tokens_and_acronym(self):
        for local, espn in (("Juventus", "Juventus"),
                            ("Atlético Madrid", "Atletico Madrid"),
                            ("ACF Fiorentina", "Fiorentina"),
                            ("AC Milan", "Milan"),
                            ("Nijmegen Eendracht Combinatie", "NEC Nijmegen")):
            with self.subTest(local=local):
                match = TeamIndex([team(espn, 147)]).match([local])
                self.assertEqual(match["espn_id"], "147")

    def test_milan_does_not_match_inter_or_reserves(self):
        index = TeamIndex([team("Inter Milan", 1), team("Milan U23", 2)])
        self.assertIsNone(index.match(["AC Milan"]))
        index = TeamIndex([team("Inter Milan", 1), team("AC Milan", 2)])
        self.assertEqual(index.match(["Milan"])["espn_id"], "2")

    def test_ambiguous_and_low_confidence_are_rejected(self):
        for candidates, query in (([team("AC Aurora", 1), team("FC Aurora", 2)], "Aurora"),
                                  ([team("Aurora Nord", 1), team("Aurora Sud", 2)], "Aurora"),
                                  ([team("NEC Breda", 1)], "Nijmegen Eendracht Combinatie"),
                                  ([team("ABC", 1)], "Alba Borgo Calcio")):
            self.assertIsNone(TeamIndex(candidates).match([query]))

    def test_duplicate_exact_alias_is_ambiguous(self):
        index = TeamIndex([team("Alpha", 1, aliases=["Aurora"]),
                           team("Beta", 2, aliases=["Aurora"])])
        self.assertIsNone(index.match(["Aurora"]))

    def test_exact_name_does_not_override_nearly_identical_rival(self):
        index = TeamIndex([team("AC Aurora", 1), team("FC Aurora", 2)])
        self.assertIsNone(index.match(["AC Aurora"]))

    def test_minor_typo_is_accepted_but_close_second_candidate_is_not(self):
        self.assertEqual(TeamIndex([team("Fiorentina", 1)]).match(["Fiorentinna"])["espn_id"], "1")
        index = TeamIndex([team("NEC Nijmegen", 147), team("Nijmegen Eendracht Combinat", 2)])
        self.assertIsNone(index.match(["Nijmegen Eendracht Combinatie"]))

    def test_id_precedes_names_and_duplicate_ids_are_rejected(self):
        index = TeamIndex([team("NEC Nijmegen", 147), team("Another Club", 2)])
        self.assertEqual(index.match(["Another Club"], "147")["name"], "NEC Nijmegen")
        self.assertIsNone(TeamIndex([team("A", 147), team("B", 147)]).match(["A"], "147"))

    def test_lists_fetched_once_and_ids_deduplicated_across_packs(self):
        response = Mock()
        response.json.return_value = {"sports": [{"leagues": [{"teams": [
            {"team": {"id": "147", "displayName": "NEC Nijmegen"}},
            {"team": {"id": "103", "displayName": "AC Milan"}},
        ]}]}]}
        session = Mock()
        session.get.return_value = response
        index, available = fetch_espn_teams(session, ["2026-27-serie-a", "2026-27-serie-a",
                                                      "2026-27-uefa-europa-league"], 2026)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(len(index.teams), 2)
        self.assertEqual(available, {"ita.1", "uefa.europa"})
        self.assertIn("Milan", index.match(["AC Milan"])["aliases"])

    def test_espn_errors_or_malformed_lists_are_best_effort(self):
        for failure in (requests.Timeout(), ValueError("bad JSON"), None):
            session = Mock()
            if failure:
                session.get.side_effect = failure
            else:
                session.get.return_value.json.return_value = {"sports": []}
            index, available = fetch_espn_teams(session, ["2026-27-serie-a"], 2026)
            self.assertEqual(index.teams, [])
            self.assertEqual(available, set())

    def test_incomplete_or_invalid_response_is_not_used_for_matching(self):
        for payload in ([], {"pageCount": 2}, {"sports": [{"leagues": [{"teams": [
            {"team": {"id": "111", "displayName": "Juventus"}}, {"team": None},
        ]}]}]}):
            session = Mock()
            session.get.return_value.json.return_value = payload
            index, available = fetch_espn_teams(session, ["2026-27-serie-a"], 2026)
            self.assertEqual(index.teams, [])
            self.assertEqual(available, set())

    def test_partial_outage_does_not_assign_from_incomplete_catalog(self):
        teams = {"juve": {"name": "Juventus", "aliases": [],
                          "packs": ["2026-27-serie-a", "2026-27-uefa-europa-league"]}}
        enrich_espn_teams(teams, {}, TeamIndex([team("Juventus", 111)]),
                          {"ita.1"}, SyncReport("2026-27"))
        self.assertNotIn("espn_id", teams["juve"])

    def test_enrichment_preserves_aliases_and_is_stable(self):
        teams = {"nec-v2001": {"name": "Nijmegen Eendracht Combinatie",
                               "aliases": ["Nijmegen Eendracht Combinatie"],
                               "packs": ["2026-27-uefa-europa-league"]}}
        previous = {"nec-v2001": {"aliases": ["Nijmegen Eendracht Combinatie", "Custom name"]}}
        index = TeamIndex([team("NEC Nijmegen", 147, aliases=["NEC Nijmegen"])])
        report = SyncReport("2026-27")
        enrich_espn_teams(teams, previous, index, {"uefa.europa"}, report)
        self.assertEqual(teams["nec-v2001"]["espn_id"], "147")
        self.assertIn("Custom name", teams["nec-v2001"]["aliases"])
        self.assertEqual(teams["nec-v2001"]["aliases"].count("NEC Nijmegen"), 1)
        saved = json.loads(json.dumps(teams))
        enrich_espn_teams(teams, saved, index, {"uefa.europa"}, SyncReport("2026-27"))
        self.assertEqual(teams, saved)

    def test_outage_keeps_verified_id_without_increasing_fclogo_errors(self):
        teams = {"juve": {"name": "Juventus", "aliases": [], "packs": ["2026-27-serie-a"]}}
        previous = {"juve": {"espn_id": "111", "aliases": ["Juve"], "espn_aliases": ["Juve"]}}
        report = SyncReport("2026-27")
        enrich_espn_teams(teams, previous, TeamIndex([]), set(), report)
        self.assertEqual(teams["juve"]["espn_id"], "111")
        self.assertEqual(report.failed, 0)

    def test_two_local_clubs_cannot_claim_same_id_or_new_alias(self):
        teams = {n: {"name": n, "aliases": [], "packs": ["2026-27-serie-a"]}
                 for n in ("AC Aurora", "FC Aurora")}
        index = TeamIndex([team("Aurora", 1, aliases=["New Alias"])])
        enrich_espn_teams(teams, {}, index, {"ita.1"}, SyncReport("2026-27"))
        for item in teams.values():
            self.assertNotIn("espn_id", item)
            self.assertNotIn("New Alias", item["aliases"])
