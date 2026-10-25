import unittest
from pathlib import Path
from PIL import Image, ImageStat
from livescore.graphics.portrait import textured


class ThirdZoomTextureTests(unittest.TestCase):
    def test_third_zoom_retains_visible_tonal_variation_and_alpha(self):
        source = Image.new('RGBA', (220, 140), (255, 255, 255, 180))
        result = textured(source, 'third', Path('assets/goal_graphics'), True)
        # Contour-line texture: subtler than the old silk, but never flat.
        self.assertGreater(ImageStat.Stat(result.convert('L')).stddev[0], 5)
        self.assertEqual(result.getchannel('A').tobytes(), source.getchannel('A').tobytes())
