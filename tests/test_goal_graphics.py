import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

import goal_graphics
import juve_bot_espn as bot


class GoalGraphicsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "backgrounds").mkdir(parents=True)
        (self.root / "overlays").mkdir(parents=True)
        (self.root / "team_logos").mkdir(parents=True)
        (self.root / "players" / "kenan_yildiz").mkdir(parents=True)
        (self.root / "players" / "guglielmo_vicario").mkdir(parents=True)

        for kit, color in (
            ("home", (20, 20, 20)),
            ("away", (90, 0, 40)),
            ("third", (5, 5, 5)),
            ("saved", (90, 35, 5)),
        ):
            Image.new("RGB", (1254, 1254), color).save(
                self.root / "backgrounds" / f"{kit}.png"
            )

        front_goal = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
        ImageDraw.Draw(front_goal).text((420, 800), "GOAL", fill=(255, 255, 255, 255))
        front_goal.save(self.root / "overlays" / "front_goal.png")
        front_goal.save(self.root / "overlays" / "front_saved.png")

        player = Image.new("RGBA", (1254, 1254), (0, 0, 0, 0))
        draw = ImageDraw.Draw(player)
        draw.rounded_rectangle((330, 80, 930, 1254), radius=120, fill=(230, 220, 210, 255))
        for filename in (
            "kenan_yildiz_pose_01_arms_crossed.png",
            "kenan_yildiz_pose_02_pointing.png",
            "kenan_yildiz_away_pink_pose_01_arms_crossed.png",
            "kenan_yildiz_away_pink_pose_02_pointing.png",
            "kenan_yildiz_third_black_pose_01_arms_crossed.png",
            "kenan_yildiz_third_black_pose_02_pointing.png",
        ):
            player.save(self.root / "players" / "kenan_yildiz" / filename)
        for filename in (
            "guglielmo_vicario_keeper_orange_pose_01_arms_crossed.png",
            "guglielmo_vicario_keeper_orange_pose_02_pointing.png",
        ):
            player.save(self.root / "players" / "guglielmo_vicario" / filename)

        self.registry = self.root / "players.json"
        self.registry.write_text(
            json.dumps({
                "players": [{
                    "name": "Kenan Yildiz",
                    "slug": "kenan_yildiz",
                    "role": "outfield",
                    "aliases": ["Kenan Yıldız", "K. Yildiz"],
                }, {
                    "name": "Guglielmo Vicario",
                    "slug": "guglielmo_vicario",
                    "role": "goalkeeper",
                    "aliases": ["G. Vicario"],
                }]
            }),
            encoding="utf-8",
        )
    def tearDown(self):
        self.tmp.cleanup()

    def test_alias_matching_ignores_accents(self):
        player = goal_graphics.find_player("Kenan Yıldız", self.registry)
        self.assertIsNotNone(player)
        self.assertEqual(player.slug, "kenan_yildiz")

    def test_kit_and_pose_select_expected_filename(self):
        player = goal_graphics.find_player("K. Yildiz", self.registry)
        self.assertEqual(
            goal_graphics.player_filename(player, "away", "pointing"),
            "kenan_yildiz_away_pink_pose_02_pointing.png",
        )

    def test_renderer_outputs_square_png(self):
        rendered = goal_graphics.render_goal_card(
            scorer_name="Kenan Yıldız",
            minute="56+2",
            home_name="Juventus",
            away_name="Inter",
            home_goals=2,
            away_goals=1,
            kit="away",
            pose="arms_crossed",
            event_key="test-event|2_1",
            asset_dir=self.root,
            registry_path=self.registry,
        )
        image = Image.open(io.BytesIO(rendered.png))
        self.assertEqual(image.size, (1254, 1254))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(rendered.kit, "away")
        self.assertEqual(rendered.pose, "arms_crossed")

    def test_dynamic_fclogo_manifest_is_preferred_and_fuzzy_matched(self):
        dynamic_dir = self.root / "team_logos" / "fclogo_cache"
        dynamic_dir.mkdir()
        Image.new("RGBA", (20, 20), (25, 80, 170, 255)).save(
            dynamic_dir / "SL-Benfica-v2025-mono.png"
        )
        (dynamic_dir / "manifest.json").write_text(
            json.dumps({
                "teams": [{
                    "name": "Sport Lisboa e Benfica",
                    "slug": "SL-Benfica-v2025",
                    "file": "SL-Benfica-v2025-mono.png",
                    "aliases": ["Sport Lisboa Benfica"],
                }]
            }),
            encoding="utf-8",
        )
        resolved = goal_graphics._local_team_logo_path("Benfica", self.root)
        self.assertEqual(resolved.parent, dynamic_dir)

    def test_team_logo_layer_uses_goal_color_and_preserves_transparency(self):
        dynamic_dir = self.root / "team_logos" / "fclogo_cache"
        dynamic_dir.mkdir()
        source_path = dynamic_dir / "Original-Club-v2026-mono.png"
        source = Image.new("RGBA", (20, 10), (15, 90, 210, 255))
        source.putpixel((10, 5), (15, 90, 210, 0))
        source.save(source_path)
        (dynamic_dir / "manifest.json").write_text(
            json.dumps({
                "teams": [{
                    "name": "Original Club",
                    "slug": "Original-Club-v2026",
                    "file": source_path.name,
                    "aliases": [],
                }]
            }),
            encoding="utf-8",
        )
        logo = goal_graphics._team_logo_layer(
            "Original Club", "", "#FF0000", self.root
        )
        self.assertIsNotNone(logo)
        self.assertEqual(logo.getpixel((0, 0))[:3], (255, 0, 0))
        self.assertEqual(logo.getpixel((logo.width // 2, logo.height // 2))[3], 0)

    def test_espn_fallback_logo_preserves_original_colors(self):
        espn_logo = Image.new("RGBA", (20, 10), (15, 90, 210, 255))
        with patch.object(
            goal_graphics, "_remote_espn_team_logo", return_value=espn_logo
        ):
            logo = goal_graphics._team_logo_layer(
                "Club non presente", "999", "#FF0000", self.root
            )
        self.assertIsNotNone(logo)
        self.assertEqual(logo.getpixel((0, 0))[:3], (15, 90, 210))

    def test_espn_fallback_stays_original_when_local_logo_is_invalid(self):
        dynamic_dir = self.root / "team_logos" / "fclogo_cache"
        dynamic_dir.mkdir()
        (dynamic_dir / "invalid.png").write_bytes(b"not an image")
        (dynamic_dir / "manifest.json").write_text(
            json.dumps({
                "teams": [{
                    "name": "Broken Club",
                    "file": "invalid.png",
                    "aliases": [],
                }]
            }),
            encoding="utf-8",
        )
        espn_logo = Image.new("RGBA", (20, 10), (15, 90, 210, 255))
        with patch.object(
            goal_graphics, "_remote_espn_team_logo", return_value=espn_logo
        ):
            logo = goal_graphics._team_logo_layer(
                "Broken Club", "999", "#FF0000", self.root
            )
        self.assertIsNotNone(logo)
        self.assertEqual(logo.getpixel((0, 0))[:3], (15, 90, 210))

    def test_overlay_tint_preserves_original_texture(self):
        source = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
        source.putpixel((0, 0), (255, 255, 255, 255))
        source.putpixel((1, 0), (110, 110, 110, 255))
        tinted = goal_graphics._tint_textured_overlay(source, "#FACA02")
        self.assertNotEqual(tinted.getpixel((0, 0))[:3], tinted.getpixel((1, 0))[:3])
        self.assertGreater(tinted.getpixel((0, 0))[0], tinted.getpixel((1, 0))[0])

    def test_saved_texture_can_ignore_dark_outline_from_source_png(self):
        source = Image.new("RGBA", (2, 2), (15, 15, 15, 255))
        texture = Image.new("RGB", (2, 2), (180, 120, 60))
        tinted = goal_graphics._tint_textured_overlay(
            source,
            "#D97C30",
            texture_source=texture,
            preserve_source_detail=False,
        )
        self.assertEqual(tinted.getpixel((0, 0))[:3], (217, 124, 48))

    def test_opaque_player_is_rejected_to_prevent_green_publish(self):
        opaque = Image.new("RGB", (1254, 1254), (0, 255, 0))
        opaque.save(
            self.root / "players" / "kenan_yildiz" /
            "kenan_yildiz_pose_01_arms_crossed.png"
        )
        with self.assertRaises(goal_graphics.GoalGraphicUnavailable):
            goal_graphics.render_goal_card(
                scorer_name="Kenan Yildiz",
                minute=10,
                home_name="Juventus",
                away_name="Inter",
                home_goals=1,
                away_goals=0,
                kit="home",
                pose="arms_crossed",
                asset_dir=self.root,
                registry_path=self.registry,
            )

    def test_goalkeeper_uses_black_background_with_orange_kit(self):
        rendered = goal_graphics.render_goal_card(
            scorer_name="Guglielmo Vicario",
            minute=90,
            home_name="Juventus",
            away_name="Inter",
            home_goals=1,
            away_goals=0,
            kit="home",
            pose="pointing",
            asset_dir=self.root,
            registry_path=self.registry,
        )
        self.assertEqual(rendered.kit, "third")
        self.assertEqual(rendered.background_path.name, "third.png")

    def test_saved_renderer_uses_orange_background_for_goalkeeper(self):
        rendered = goal_graphics.render_saved_card(
            goalkeeper_name="G. Vicario",
            minute=72,
            home_name="Juventus",
            away_name="Inter",
            home_goals=1,
            away_goals=0,
            pose="arms_crossed",
            asset_dir=self.root,
            registry_path=self.registry,
        )
        self.assertEqual(rendered.kit, "saved")
        self.assertEqual(rendered.background_path.name, "saved.png")

    def test_saved_renderer_rejects_outfield_player(self):
        with self.assertRaises(goal_graphics.GoalGraphicUnavailable):
            goal_graphics.render_saved_card(
                goalkeeper_name="Kenan Yildiz",
                minute=72,
                home_name="Juventus",
                away_name="Inter",
                home_goals=1,
                away_goals=0,
                asset_dir=self.root,
                registry_path=self.registry,
            )

    def test_missing_approved_goal_overlay_falls_back_safely(self):
        (self.root / "overlays" / "front_goal.png").unlink()
        with self.assertRaises(goal_graphics.GoalGraphicUnavailable):
            goal_graphics.render_goal_card(
                scorer_name="Kenan Yildiz",
                minute=10,
                home_name="Juventus",
                away_name="Inter",
                home_goals=1,
                away_goals=0,
                kit="home",
                pose="arms_crossed",
                asset_dir=self.root,
                registry_path=self.registry,
            )

    def test_bot_never_renders_for_opponent_goal(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card"
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="Opponent Player",
                goal_type="goal",
                scoring_team_id="999",
                minute=12,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=0,
                away_goals=1,
                league_slug="ita.1",
                league_name="Serie A",
                event_key="test|0_1",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_friendly_goal_never_renders_a_card(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card"
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="Kenan Yildiz",
                goal_type="goal",
                scoring_team_id="111",
                minute=12,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                league_slug="club.friendly",
                league_name="Club Friendly",
                event_key="friendly-goal",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_own_goal_team_is_inverted_before_juventus_graphic_logic(self):
        self.assertEqual(
            bot.goal_scoring_team_id(
                {"type": "own goal", "team_id": "999"}, "111", "999"
            ),
            "111",
        )
        self.assertEqual(
            bot.goal_scoring_team_id(
                {"type": "own goal", "team_id": "111"}, "111", "999"
            ),
            "999",
        )

    def test_juventus_own_goal_never_renders_a_player_card(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card"
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="Kenan Yildiz",
                goal_type="own goal",
                scoring_team_id="999",
                minute=12,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=0,
                away_goals=1,
                league_slug="ita.1",
                league_name="Serie A",
                event_key="juve-own-goal",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_own_goal_benefiting_juventus_prepares_anonymous_card(self):
        anonymous_card = SimpleNamespace(
            player=None,
            scorer_name="Opponent Player",
            kit="home",
            pose="arms_crossed",
        )
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card", return_value=anonymous_card
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="Opponent Player",
                goal_type="own goal",
                scoring_team_id="111",
                minute=48,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                league_slug="ita.1",
                league_name="Serie A",
                event_key="benefiting-own-goal",
            )
        self.assertIs(result, anonymous_card)
        self.assertEqual(render.call_args.kwargs["goal_type"], "own goal")

    def test_unknown_juventus_scorer_keeps_original_caption_and_gets_card(self):
        scorer_line, assist_line = bot.goal_player_lines(
            "New Player", "Kenan Yildiz", "goal", "111"
        )
        self.assertIn("N. Player", scorer_line)
        self.assertNotIn("AUTOGOL", scorer_line)
        self.assertEqual(assist_line, "")

        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics,
            "render_goal_card",
            return_value=SimpleNamespace(
                player=None,
                scorer_name="New Player",
                kit="home",
                pose="pointing",
            ),
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="New Player",
                goal_type="goal",
                scoring_team_id="111",
                minute=12,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                league_slug="ita.1",
                league_name="Serie A",
                event_key="unknown-scorer",
            )
        self.assertIsNotNone(result)
        render.assert_called_once()
        self.assertEqual(render.call_args.kwargs["goal_type"], "goal")

    def test_juventus_benefiting_own_goal_keeps_original_caption_style(self):
        scorer_line, assist_line = bot.goal_player_lines(
            "Opponent Player", "Other Player", "own goal", "111"
        )
        self.assertIn("(Autogol)", scorer_line)
        self.assertNotIn("(AUTOGOL)", scorer_line)
        self.assertEqual(assist_line, "")

    def test_penalty_goal_keeps_original_caption_style(self):
        scorer_line, _ = bot.goal_player_lines(
            "Kenan Yildiz", "", "penalty goal", "111"
        )
        self.assertIn("(Rig.)", scorer_line)
        self.assertNotIn("(RIGORE)", scorer_line)

    def test_unknown_scorer_renders_card_without_player_cutout(self):
        rendered = goal_graphics.render_goal_card(
            scorer_name="New Player",
            minute=60,
            home_name="Juventus",
            away_name="Inter",
            home_goals=2,
            away_goals=0,
            kit="home",
            asset_dir=self.root,
            registry_path=self.registry,
        )
        self.assertIsNone(rendered.player)
        self.assertIsNone(rendered.player_path)
        self.assertEqual(rendered.scorer_name, "New Player")
        self.assertTrue(rendered.png.startswith(b"\x89PNG"))

    def test_graphic_suffixes_are_uppercase_inside_card_only(self):
        with patch.object(goal_graphics, "_centered_tracked_text") as draw_name:
            own_goal = goal_graphics.render_goal_card(
                scorer_name="Opponent Player",
                goal_type="own goal",
                minute=48,
                home_name="Juventus",
                away_name="Inter",
                home_goals=1,
                away_goals=0,
                kit="home",
                asset_dir=self.root,
                registry_path=self.registry,
            )
        self.assertIsNone(own_goal.player)
        self.assertEqual(draw_name.call_args.args[2], "OPPONENT PLAYER (AUTOGOL)")

        with patch.object(goal_graphics, "_centered_tracked_text") as draw_name:
            penalty = goal_graphics.render_goal_card(
                scorer_name="Kenan Yildiz",
                goal_type="penalty goal",
                minute=31,
                home_name="Juventus",
                away_name="Inter",
                home_goals=2,
                away_goals=0,
                kit="away",
                asset_dir=self.root,
                registry_path=self.registry,
            )
        self.assertIsNotNone(penalty.player)
        self.assertEqual(draw_name.call_args.args[2], "KENAN YILDIZ (RIGORE)")

    def test_shootout_goal_never_renders_a_goal_card(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card"
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={},
                scorer_name="Kenan Yildiz",
                goal_type="shootout goal",
                scoring_team_id="111",
                minute=120,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=1,
                league_slug="uefa.champions",
                league_name="UEFA Champions League",
                event_key="shootout-goal",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_scorer_correction_replaces_existing_goal_photo(self):
        corrected = SimpleNamespace(png=b"new-player-card")
        with patch.object(bot, "edit_telegram_goal_photo", return_value=True) as edit:
            ok, message_id, is_photo = bot.replace_corrected_goal_message(
                321, True, "corrected caption", corrected
            )
        self.assertTrue(ok)
        self.assertEqual(message_id, 321)
        self.assertTrue(is_photo)
        edit.assert_called_once_with(321, "corrected caption", b"new-player-card")

    def test_correction_falls_back_to_text_when_new_card_is_unavailable(self):
        with patch.object(bot, "send_telegram_get_id", return_value=654), patch.object(
            bot, "delete_telegram_message"
        ) as delete:
            ok, message_id, is_photo = bot.replace_corrected_goal_message(
                321, True, "own goal text", None
            )
        self.assertTrue(ok)
        self.assertEqual(message_id, 654)
        self.assertFalse(is_photo)
        delete.assert_called_once_with(321)

    def test_correction_from_text_adds_photo_to_same_message(self):
        corrected = SimpleNamespace(png=b"registered-player-card")
        with patch.object(
            bot, "edit_telegram_goal_photo", return_value=True
        ) as edit_photo, patch.object(bot, "delete_telegram_message") as delete:
            ok, message_id, is_photo = bot.replace_corrected_goal_message(
                654, False, "corrected caption", corrected
            )
        self.assertTrue(ok)
        self.assertEqual(message_id, 654)
        self.assertTrue(is_photo)
        edit_photo.assert_called_once_with(
            654, "corrected caption", b"registered-player-card"
        )
        delete.assert_not_called()

    def test_missing_scorer_starts_as_text_until_photo_is_available(self):
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_goal_card"
        ) as render:
            result = bot.prepara_grafica_goal(
                data_espn={}, scorer_name="", goal_type="goal",
                scoring_team_id="111", minute=82,
                home_name="Juventus", away_name="Inter",
                home_id="111", away_id="999",
                home_goals=1, away_goals=0,
                league_slug="ita.1", league_name="Serie A",
                event_key="missing-scorer",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_finds_juve_goalkeeper_from_espn_roster(self):
        data = {"rosters": [{
            "team": {"id": "111"},
            "roster": [{
                "athlete": {"displayName": "Guglielmo Vicario"},
                "position": {"abbreviation": "GK"},
                "starter": True,
            }],
        }]}
        self.assertEqual(bot.trova_portiere_juve(data), "Guglielmo Vicario")

    def test_saved_card_is_only_prepared_for_opponent_penalty_saved(self):
        saved_event = {
            "type": "penalty saved",
            "team_id": "999",
            "player_name": "Opponent Taker",
        }
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_saved_card"
        ) as render:
            render.return_value.player.name = "Guglielmo Vicario"
            render.return_value.pose = "arms_crossed"
            result = bot.prepara_grafica_parata_rigore(
                data_espn={},
                penalty_event=saved_event,
                goalkeeper_name="Guglielmo Vicario",
                minute=72,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                event_key="saved-test",
            )
        self.assertIs(result, render.return_value)
        render.assert_called_once()

    def test_penalty_missed_never_prepares_saved_card(self):
        missed_event = {
            "type": "penalty missed",
            "team_id": "999",
            "player_name": "Opponent Taker",
        }
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_saved_card"
        ) as render:
            result = bot.prepara_grafica_parata_rigore(
                data_espn={},
                penalty_event=missed_event,
                goalkeeper_name="Guglielmo Vicario",
                minute=72,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                event_key="missed-test",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_friendly_penalty_save_never_renders_saved_card(self):
        saved_event = {
            "type": "penalty saved",
            "team_id": "999",
            "player_name": "Opponent Taker",
        }
        with patch.object(bot, "GOAL_GRAPHICS_ENABLED", True), patch.object(
            bot.goal_graphics, "render_saved_card"
        ) as render:
            result = bot.prepara_grafica_parata_rigore(
                data_espn={},
                penalty_event=saved_event,
                goalkeeper_name="Guglielmo Vicario",
                minute=72,
                home_name="Juventus",
                away_name="Inter",
                home_id="111",
                away_id="999",
                home_goals=1,
                away_goals=0,
                event_key="friendly-saved",
                league_slug="club.friendly",
                league_name="Club Friendly",
            )
        self.assertIsNone(result)
        render.assert_not_called()

    def test_kit_comes_from_espn_uniform(self):
        payload = {
            "header": {"competitions": [{"competitors": []}]},
            "boxscore": {"teams": [{
                "homeAway": "home",
                "team": {"uniform": {"type": "third", "color": "111111"}},
            }]},
        }
        self.assertEqual(
            bot.rileva_kit_juve(
                payload, "111", "999", "Juventus", "Inter", "ita.1", "Serie A"
            ),
            "third",
        )


if __name__ == "__main__":
    unittest.main()
