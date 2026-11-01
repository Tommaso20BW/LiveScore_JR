import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from livescore.core import team_names, team_overrides
from livescore.graphics import goal


def png(path, color=(0, 0, 0, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (20, 20), color).save(path)


class TeamOverridesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.assets = Path(self.tmp.name)
        logos = self.assets / "team_logos"
        png(logos / "serie-a" / "inter.png")
        png(logos / "serie-a" / "napoli.png")
        (logos / "manifest.json").write_text(json.dumps({"teams": [
            {"name": "FC Inter Milan", "aliases": ["FC Inter Milan"], "file": "serie-a/inter.png"},
            {"name": "SSC Napoli", "aliases": ["SSC Napoli", "Napoli"], "file": "serie-a/napoli.png"},
        ]}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, teams):
        path = team_overrides.overrides_path(self.assets)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "teams": teams}), encoding="utf-8")

    def logo(self, name):
        return goal._local_team_logo_path(name, self.assets)

    def test_without_file_nothing_changes(self):
        self.assertEqual(team_overrides.load(self.assets), {})
        self.assertIsNone(self.logo("Internazionale"))
        self.assertEqual(self.logo("FC Inter Milan").name, "inter.png")
        rows = [{"name": "FC Inter Milan", "aliases": []}]
        self.assertEqual(team_overrides.apply(rows, self.assets), rows)

    def test_espn_alias_points_to_fclogo_logo(self):
        self.write({"fc inter milan": {"base": "FC Inter Milan", "aliases": ["Internazionale"]}})
        self.assertEqual(self.logo("Internazionale").name, "inter.png")
        self.assertEqual(self.logo("SSC Napoli").name, "napoli.png")

    def test_custom_logo_wins_and_removing_it_restores_fclogo(self):
        png(self.assets / "team_overrides" / "logos" / "inter.png")
        self.write({"fc inter milan": {"base": "FC Inter Milan", "logo": "logos/inter.png", "name": "Inter"}})
        self.assertIn("team_overrides", str(self.logo("FC Inter Milan")))
        self.assertIn("team_overrides", str(self.logo("Inter")))
        self.write({"fc inter milan": {"base": "FC Inter Milan", "name": "Inter"}})
        self.assertEqual(self.logo("FC Inter Milan").name, "inter.png")

    def test_custom_logo_and_name_apply_to_every_fclogo_alias(self):
        png(self.assets / "team_overrides" / "logos" / "napoli.png")
        self.write({"ssc napoli": {"base": "SSC Napoli", "logo": "logos/napoli.png", "name": "Napoli Test"}})
        # "Napoli" è un alias del catalogo FCLogo, non scritto nelle correzioni.
        self.assertIn("team_overrides", str(self.logo("Napoli")))
        self.assertEqual(team_overrides.display_name("Napoli", self.assets), "Napoli Test")
        self.assertIsNone(team_overrides.display_name("FC Inter Milan", self.assets))

    def test_missing_custom_file_falls_back_to_fclogo(self):
        self.write({"fc inter milan": {"base": "FC Inter Milan", "logo": "logos/missing.png"}})
        self.assertEqual(self.logo("FC Inter Milan").name, "inter.png")

    def test_new_team_needs_name_and_logo(self):
        png(self.assets / "team_overrides" / "logos" / "chelsea.png")
        self.write({"new:chelsea": {"base": None, "name": "Chelsea", "aliases": ["Chelsea FC"], "logo": "logos/chelsea.png"},
                    "new:broken": {"base": None, "name": "Senza logo"}})
        self.assertEqual(list(team_overrides.load(self.assets)), ["new:chelsea"])
        self.assertIn("chelsea.png", str(self.logo("Chelsea FC")))
        rows = team_overrides.apply([{"name": "SSC Napoli", "aliases": []}], self.assets)
        self.assertEqual([r["name"] for r in rows], ["SSC Napoli", "Chelsea"])
        self.assertTrue(rows[1]["manual"])

    def test_apply_marks_changes_without_touching_originals(self):
        self.write({"fc inter milan": {"base": "FC Inter Milan", "name": "Inter", "aliases": ["Internazionale"]}})
        original = [{"name": "FC Inter Milan", "aliases": ["FC Inter Milan"]}]
        rows = team_overrides.apply(original, self.assets)
        self.assertEqual(original[0]["aliases"], ["FC Inter Milan"])
        self.assertEqual(rows[0]["aliases"], ["FC Inter Milan", "Internazionale"])
        self.assertEqual(rows[0]["aliases_fclogo"], ["FC Inter Milan"])
        self.assertEqual(rows[0]["display_name"], "Inter")

    def test_empty_entries_are_dropped(self):
        self.write({"fc inter milan": {"base": "FC Inter Milan", "name": "FC Inter Milan", "aliases": []}})
        self.assertEqual(team_overrides.load(self.assets), {})

    def test_broken_file_is_ignored(self):
        path = team_overrides.overrides_path(self.assets)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{rotto", encoding="utf-8")
        self.assertEqual(team_overrides.load(self.assets), {})
        self.assertEqual(self.logo("FC Inter Milan").name, "inter.png")

    def test_display_name_overrides_teams_json(self):
        self.write({"fc inter milan": {"base": "FC Inter Milan", "name": "Inter", "aliases": ["Internazionale"]}})
        original = team_overrides.ASSETS_DIR
        try:
            team_overrides.ASSETS_DIR = self.assets
            team_overrides.display_name.__defaults__ = (self.assets,)
            self.assertEqual(team_names.translate_team("Internazionale"), "Inter")
        finally:
            team_overrides.display_name.__defaults__ = (original,)
        self.assertNotEqual(team_names.translate_team("Internazionale"), "")


if __name__ == "__main__":
    unittest.main()
