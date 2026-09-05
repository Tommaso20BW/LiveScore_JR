import unittest

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
