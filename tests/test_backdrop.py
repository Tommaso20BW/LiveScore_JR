import unittest

from PIL import Image

from livescore.graphics import backdrop


class BackdropTest(unittest.TestCase):
    def test_light_background_gets_shadow_dark_does_not(self):
        light = backdrop.phase_shadow(Image.new('RGB', (600, 800), (240, 240, 240)))
        dark = backdrop.phase_shadow(Image.new('RGB', (600, 800), (15, 15, 20)))
        self.assertGreater(light['strength'], 0.9)
        self.assertEqual(tuple(light['color']), (0, 0, 0))
        self.assertEqual(dark['strength'], 0)


if __name__ == '__main__':
    unittest.main()
