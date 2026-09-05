import ast
import copy
import unittest
from pathlib import Path

from fclogo_sync import preserve_manifest_aliases


ROOT = Path(__file__).resolve().parents[1]


class ManualAliasTests(unittest.TestCase):
    def record(self, slug, federation="figc", aliases=None):
        return {"slug": slug, "detail_path": f"/{federation}/club/{slug}",
                "aliases": aliases or ["FC Aurora"]}

    def test_aliases_survive_version_change_and_are_deduplicated(self):
        old = self.record("FC-Aurora-v2025", aliases=["FC Aurora", "ESPN Name"])
        new = self.record("FC-Aurora-v2027-minor")
        teams = {new["slug"]: new}
        preserve_manifest_aliases(teams, {old["slug"]: old})
        self.assertEqual(new["aliases"], ["FC Aurora", "ESPN Name"])
        saved = copy.deepcopy(teams)
        preserve_manifest_aliases(teams, saved)
        self.assertEqual(teams, saved)

    def test_different_federation_or_changed_name_does_not_inherit(self):
        old = self.record("FC-Aurora-v2025", aliases=["My alias"])
        for new in (self.record("FC-Aurora-v2027", "fff"),
                    self.record("FC-Aurora-Nord-v2027")):
            preserve_manifest_aliases({new["slug"]: new}, {old["slug"]: old})
            self.assertNotIn("My alias", new["aliases"])

    def test_ambiguous_previous_versions_do_not_transfer_aliases(self):
        a = self.record("FC-Aurora-v2024", aliases=["Alpha"])
        b = self.record("FC-Aurora-v2025", aliases=["Beta"])
        new = self.record("FC-Aurora-v2027")
        preserve_manifest_aliases({new["slug"]: new}, {a["slug"]: a, b["slug"]: b})
        self.assertEqual(new["aliases"], ["FC Aurora"])

    def test_manual_alias_removal_is_respected(self):
        old = self.record("FC-Aurora-v2025", aliases=["FC Aurora"])
        old["espn_aliases"] = ["Deleted alias"]
        old["espn_id"] = "123"
        new = copy.deepcopy(old)
        preserve_manifest_aliases({new["slug"]: new}, {old["slug"]: old})
        self.assertNotIn("Deleted alias", new["aliases"])
        self.assertNotIn("espn_id", new)
        self.assertNotIn("espn_aliases", new)

    def test_all_live_goal_saved_calls_pass_original_espn_names(self):
        tree = ast.parse((ROOT / "juve_bot_espn.py").read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id in
                 ("prepara_grafica_goal", "prepara_grafica_parata_rigore")]
        self.assertEqual(len(calls), 4)  # iniziale, live, correzione, SAVED
        for call in calls:
            args = {kw.arg: kw.value for kw in call.keywords}
            self.assertEqual(args["home_name"].id, "home_name_raw")
            self.assertEqual(args["away_name"].id, "away_name_raw")

    def test_workflow_caches_only_pngs_not_manual_manifest(self):
        workflow = (ROOT / ".github/workflows/main_espn.yml").read_text(encoding="utf-8")
        self.assertIn("path: assets/goal_graphics/team_logos/fclogo_cache/*.png", workflow)
        self.assertNotIn("fclogo-team-logos-", workflow)
