import unittest

import juve_bot_espn as bot


def make_payload(*, team_one, team_two, cell_one, cell_two, stat_name="Expected Goals"):
    return {
        "page": {
            "content": {
                "gamepackage": {
                    "mtchStatsGrph": {
                        "teams": {
                            "teamOne": team_one,
                            "teamTwo": team_two,
                        },
                        "stats": [
                            {
                                "data": [
                                    {
                                        "name": stat_name,
                                        "teamOne": cell_one,
                                        "teamTwo": cell_two,
                                    }
                                ]
                            }
                        ],
                    }
                }
            }
        }
    }


class ExpectedGoalsParsingTests(unittest.TestCase):
    def test_maps_values_by_team_id_not_by_team_order(self):
        payload = make_payload(
            team_one={"id": "4057", "isHome": True},
            team_two={"id": "111", "isHome": False},
            cell_one={"value": 0.139, "displayValue": "0.14"},
            cell_two={"value": 1.168, "displayValue": "1.17"},
        )

        self.assertEqual(
            bot._estrai_xg_mtchstatsgraph(payload, home_id="4057", away_id="111"),
            ("0.14", "1.17"),
        )

    def test_zero_is_a_valid_xg_value(self):
        payload = make_payload(
            team_one={"id": "111"},
            team_two={"id": "4057"},
            cell_one={"value": 0, "displayValue": "0.00"},
            cell_two={"value": 0.42, "displayValue": "0.42"},
        )

        self.assertEqual(
            bot._estrai_xg_mtchstatsgraph(payload, home_id="111", away_id="4057"),
            ("0.00", "0.42"),
        )

    def test_display_value_is_used_when_numeric_value_is_missing(self):
        payload = make_payload(
            team_one={"id": "111"},
            team_two={"id": "4057"},
            cell_one={"value": None, "displayValue": "0.35"},
            cell_two={"value": None, "displayValue": "0.00"},
        )

        self.assertEqual(
            bot._estrai_xg_mtchstatsgraph(payload, home_id="111", away_id="4057"),
            ("0.35", "0.00"),
        )

    def test_omits_xg_when_one_team_cell_is_missing(self):
        payload = make_payload(
            team_one={"id": "111"},
            team_two={"id": "4057"},
            cell_one={"value": 0.35, "displayValue": "0.35"},
            cell_two={},
        )

        self.assertIsNone(
            bot._estrai_xg_mtchstatsgraph(payload, home_id="111", away_id="4057")
        )

    def test_omits_xg_when_expected_goals_record_is_absent(self):
        payload = make_payload(
            team_one={"id": "111"},
            team_two={"id": "4057"},
            cell_one={"value": 7},
            cell_two={"value": 5},
            stat_name="Total Shots",
        )

        self.assertIsNone(
            bot._estrai_xg_mtchstatsgraph(payload, home_id="111", away_id="4057")
        )


if __name__ == "__main__":
    unittest.main()
