import unittest

from livescore.graphics import flags


class FlagEmojiTests(unittest.TestCase):
    def test_nations_get_flag_emoji(self):
        self.assertEqual(flags.emoji_for("Italy"), "\U0001F1EE\U0001F1F9")
        self.assertEqual(flags.emoji_for("Francia"), "\U0001F1EB\U0001F1F7")
        self.assertEqual(flags.emoji_for("England"),
                         "\U0001F3F4\U000E0065\U000E006E\U000E0067\U000E007F")

    def test_clubs_get_nothing(self):
        self.assertEqual(flags.emoji_for("Juventus"), "")
        self.assertEqual(flags.emoji_for("Inter"), "")


if __name__ == "__main__":
    unittest.main()
