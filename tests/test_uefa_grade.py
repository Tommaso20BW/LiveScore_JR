import unittest

import numpy as np
from PIL import Image

from livescore.graphics import portrait
from livescore.graphics.uefa_grade import PRESETS, grade


def sample():
    """Foto finta: sfumatura di colori con bordo trasparente e alfa intermedio."""
    y, x = np.mgrid[0:120, 0:90]
    rgba = np.zeros((120, 90, 4), np.uint8)
    rgba[..., 0] = x * 2.8
    rgba[..., 1] = y * 2.1
    rgba[..., 2] = 255 - x * 2.8
    rgba[..., 3] = 255
    rgba[:10] = 0
    rgba[10:20, :, 3] = 128
    rgba[60:80, 30:60, :3] = (190, 130, 100)        # tono pelle
    return Image.fromarray(rgba, 'RGBA')


class UefaGradeTest(unittest.TestCase):
    def test_competitions_get_their_preset(self):
        self.assertEqual(portrait.theme('home', 'uefa.champions'), 'ucl')
        self.assertEqual(portrait.theme('home', 'uefa.super_cup'), 'usc')
        self.assertEqual(portrait.theme('home', 'uefa.europa'), 'uel')
        self.assertEqual(portrait.theme('home', 'uefa.europa.conf'), 'conference')
        self.assertEqual(set(PRESETS), {'ucl', 'usc', 'uel', 'conference'})

    def test_other_competitions_untouched(self):
        img = sample()
        for comp in ('ita.1', 'ita.coppa_italia', 'ita.super_cup', 'fifa.cwc', 'friendly'):
            self.assertIs(grade(img, portrait.theme('home', comp)), img, comp)
        self.assertIs(grade(img, 'ita_home'), img)

    def test_size_and_transparency_kept(self):
        img = sample()
        for key in PRESETS:
            out = grade(img, key)
            self.assertEqual(out.size, img.size)
            self.assertEqual(out.mode, 'RGBA')
            np.testing.assert_array_equal(np.asarray(out)[..., 3], np.asarray(img)[..., 3])

    def test_colour_direction(self):
        img = sample()
        base = np.asarray(img.convert('RGB'), np.float32)[20:].mean((0, 1))
        shift = {k: np.asarray(grade(img, k).convert('RGB'), np.float32)[20:].mean((0, 1)) - base for k in PRESETS}
        self.assertGreater(shift['ucl'][2] - shift['ucl'][0], 5)            # blu freddo
        self.assertGreater(shift['uel'][0] - shift['uel'][2], 5)            # ambra calda
        self.assertGreater(shift['conference'][1] - shift['conference'][0], 5)   # verde
        self.assertGreater(shift['usc'][2] - shift['usc'][0], 1)            # Supercoppa: blu, più leggera
        self.assertLess(shift['usc'][2] - shift['usc'][0], shift['ucl'][2] - shift['ucl'][0])

    def test_skin_stays_close(self):
        img = sample()
        skin = np.asarray(img.convert('RGB'), np.float32)[60:80, 30:60]
        for key in PRESETS:
            out = np.asarray(grade(img, key).convert('RGB'), np.float32)[60:80, 30:60]
            self.assertLess(np.abs(out - skin).mean(), 25, key)


    def test_set_light_face_brighter_than_body(self):
        flat = Image.new('RGBA', (60, 200), (128, 128, 128, 255))
        for key in PRESETS:
            a = np.asarray(grade(flat, key).convert('L'), np.float32)
            self.assertGreater(a[10:50].mean(), a[160:195].mean() + 8, key)

    def test_kit_white_and_black_stay_neutral(self):
        for value in (245, 15):
            flat = Image.new('RGBA', (40, 40), (value, value, value, 255))
            for key in PRESETS:
                px = np.asarray(grade(flat, key, relight=False).convert('RGB'), np.int16)[20, 20]
                self.assertLessEqual(px.max() - px.min(), 4, (key, value, px))

    def test_relight_off_keeps_even_light(self):
        # ritaglio della testa sopra la cornice: niente luce da set, altrimenti stacca dal resto
        flat = Image.new('RGBA', (60, 200), (128, 128, 128, 255))
        a = np.asarray(grade(flat, 'ucl', relight=False).convert('L'), np.float32)
        self.assertLess(abs(a[20:60].mean() - a[140:180].mean()), 3)


if __name__ == '__main__':
    unittest.main()
