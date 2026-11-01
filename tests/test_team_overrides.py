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


class DropSupersededLogosTests(unittest.TestCase):
    def _write(self, teams):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "team_overrides" / "logos").mkdir(parents=True)
        for entry in teams.values():
            if entry.get("logo"):
                (root / "team_overrides" / entry["logo"]).write_bytes(b"png")
        (root / "team_overrides" / "overrides.json").write_text(
            json.dumps({"version": 1, "teams": teams}), encoding="utf-8")
        return root

    def _teams(self, root):
        return json.loads((root / "team_overrides" / "overrides.json").read_text(encoding="utf-8"))["teams"]

    def test_fresh_mono_removes_only_the_manual_logo(self):
        root = self._write({
            "lecce": {"base": "Lecce", "name": "US Lecce", "aliases": ["Lecce US"], "logo": "logos/lecce.png"},
            "juve": {"base": "Juventus", "logo": "logos/juve.png"},
        })
        cleared = team_overrides.drop_superseded_logos([{"name": "Lecce", "aliases": []}], root)
        self.assertEqual(cleared, ["US Lecce"])
        teams = self._teams(root)
        self.assertEqual(teams["lecce"], {"base": "Lecce", "name": "US Lecce", "aliases": ["Lecce US"]})
        self.assertFalse((root / "team_overrides" / "logos" / "lecce.png").exists())
        self.assertEqual(teams["juve"]["logo"], "logos/juve.png")
        self.assertTrue((root / "team_overrides" / "logos" / "juve.png").exists())

    def test_logo_only_correction_disappears(self):
        root = self._write({"juve": {"base": "Juventus", "logo": "logos/juve.png"}})
        self.assertEqual(team_overrides.drop_superseded_logos([{"name": "Juventus"}], root), ["Juventus"])
        self.assertEqual(self._teams(root), {})

    def test_manual_new_team_is_linked_to_the_new_fclogo_team(self):
        root = self._write({"pisa": {"base": None, "name": "Pisa", "aliases": ["Pisa SC"], "logo": "logos/pisa.png"}})
        cleared = team_overrides.drop_superseded_logos([{"name": "AC Pisa 1909", "aliases": ["Pisa"]}], root)
        self.assertEqual(cleared, ["Pisa"])
        self.assertEqual(self._teams(root)["pisa"], {"base": "AC Pisa 1909", "name": "Pisa", "aliases": ["Pisa SC"]})

    def test_nothing_fresh_leaves_file_untouched(self):
        root = self._write({"juve": {"base": "Juventus", "logo": "logos/juve.png"}})
        before = (root / "team_overrides" / "overrides.json").read_bytes()
        self.assertEqual(team_overrides.drop_superseded_logos([{"name": "Lecce"}], root), [])
        self.assertEqual((root / "team_overrides" / "overrides.json").read_bytes(), before)
