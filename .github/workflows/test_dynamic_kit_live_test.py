import unittest
from unittest.mock import Mock

import dynamic_kit_live_test as sim


class DynamicKitStateTests(unittest.TestCase):
    def make_state(self):
        state = sim.KitState(event_id="SIM123", fallback_kit="away", active_kit="away")
        state.ensure_compat()
        return state

    def test_uniform_missing_uses_fallback(self):
        state = self.make_state()
        sim.set_espn_kit(state, None)
        self.assertEqual(state.active_kit, "away")

    def test_espn_publishes_uniform_before_kickoff(self):
        state = self.make_state()
        sim.set_espn_kit(state, "third")
        self.assertEqual(state.espn_kit, "third")
        self.assertEqual(state.active_kit, "third")

    def test_espn_changes_kit_during_live(self):
        state = self.make_state()
        sim.set_espn_kit(state, "home")
        old, new, changed = sim.set_espn_kit(state, "third")
        self.assertEqual((old, new, changed), ("home", "third", True))

    def test_auto_follows_espn(self):
        state = self.make_state()
        sim.set_espn_kit(state, "third")
        self.assertEqual(state.kit_mode, "auto")
        self.assertEqual(sim.get_active_kit(state), "third")

    def test_manual_ignores_later_espn_change(self):
        state = self.make_state()
        sim.set_manual_kit(state, "home")
        sim.set_espn_kit(state, "third")
        self.assertEqual(state.espn_kit, "third")
        self.assertEqual(state.active_kit, "home")

    def test_manual_buttons_set_active_kit(self):
        for kit in sim.VALID_KITS:
            state = self.make_state()
            handled, changed, _ = sim.apply_callback(
                state, f"cb-{kit}", f"kit:{state.event_id}:{kit}"
            )
            self.assertTrue(handled)
            self.assertEqual(state.kit_mode, "manual")
            self.assertEqual(state.manual_kit, kit)
            self.assertEqual(state.active_kit, kit)

    def test_auto_removes_override(self):
        state = self.make_state()
        sim.set_espn_kit(state, "third")
        sim.set_manual_kit(state, "home")
        handled, changed, _ = sim.apply_callback(
            state, "cb-auto", f"kit:{state.event_id}:auto"
        )
        self.assertTrue(handled)
        self.assertTrue(changed)
        self.assertEqual(state.kit_mode, "auto")
        self.assertIsNone(state.manual_kit)
        self.assertEqual(state.active_kit, "third")

    def test_change_kit_edits_existing_media(self):
        state = self.make_state()
        state.active_kit = "third"
        state.kit_media = {
            "goal": {
                "message_id": 123,
                "type": "goal",
                "caption": "goal",
                "kit": "away",
            }
        }
        tg = Mock()
        tg.edit_photo.return_value = True
        render = Mock(return_value=b"png")
        edited = sim.refresh_all_media(tg, state, None, render_func=render)
        self.assertEqual(edited, 1)
        tg.edit_photo.assert_called_once_with(123, "goal", b"png")
        self.assertEqual(state.kit_media["goal"]["kit"], "third")

    def test_failed_edit_keeps_old_kit_for_retry(self):
        state = self.make_state()
        state.active_kit = "third"
        state.kit_media = {
            "goal": {
                "message_id": 123,
                "type": "goal",
                "caption": "goal",
                "kit": "away",
            }
        }
        tg = Mock()
        tg.edit_photo.return_value = False
        edited = sim.refresh_all_media(
            tg, state, None, render_func=Mock(return_value=b"png")
        )
        self.assertEqual(edited, 0)
        self.assertEqual(state.kit_media["goal"]["kit"], "away")
        self.assertIsNotNone(state.kit_media["goal"]["last_edit_error"])

    def test_callback_for_other_event_is_ignored(self):
        state = self.make_state()
        handled, changed, _ = sim.apply_callback(
            state, "cb-x", "kit:OLD999:home"
        )
        self.assertFalse(handled)
        self.assertFalse(changed)
        self.assertEqual(state.active_kit, "away")

    def test_duplicate_callback_is_not_reprocessed(self):
        state = self.make_state()
        data = f"kit:{state.event_id}:home"
        first = sim.apply_callback(state, "same-id", data)
        second = sim.apply_callback(state, "same-id", data)
        self.assertTrue(first[0])
        self.assertFalse(second[0])

    def test_old_state_defaults_are_compatible(self):
        state = sim.KitState(
            event_id="SIM123",
            fallback_kit="away",
            active_kit="nonsense",
            kit_mode="broken",
            manual_kit="banana",
            kit_media=None,
            processed_callback_ids=[],
        )
        state.ensure_compat()
        self.assertEqual(state.kit_mode, "auto")
        self.assertEqual(state.active_kit, "away")
        self.assertEqual(state.kit_media, {})
        self.assertEqual(state.processed_callback_ids, set())

    def test_recap_and_keyboard_show_correct_mode(self):
        state = self.make_state()
        sim.set_espn_kit(state, "third")
        sim.set_manual_kit(state, "home")
        text = sim.recap_text(state)
        keyboard = sim.keyboard_for(state)
        self.assertIn("Kit Juventus: <b>Home</b>", text)
        self.assertIn("Modalità kit: <b>MANUAL</b>", text)
        self.assertIn("ESPN uniform: <b>Third</b>", text)
        self.assertEqual(keyboard["inline_keyboard"][0][0]["text"], "✅ HOME")


if __name__ == "__main__":
    unittest.main()
