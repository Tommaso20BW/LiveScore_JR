import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from livescore.graphics import phase_layers as pl


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


class PhaseLayersTest(unittest.TestCase):
    def test_background_always_covers_page(self):
        left, top, width, height = pl.box((1000, 1000), {'x': 0.9, 'y': -0.9, 'zoom': 1})
        self.assertLessEqual(left, 0)
        self.assertLessEqual(top, 0)
        self.assertGreaterEqual(left + width, pl.SIZE[0] - 0.01)
        self.assertGreaterEqual(top + height, pl.SIZE[1] - 0.01)

    def test_person_can_move_freely(self):
        left, top, _, _ = pl.box((1086, 1448), {'x': 0.25, 'zoom': 0.5}, cover=False)
        self.assertGreater(left, 0)
        self.assertGreater(top, 0)

    def test_uploaded_transparent_person_is_used_as_is(self):
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (200, 200, 400, 600))
        with tempfile.TemporaryDirectory() as tmp, patch.object(pl, 'cutout') as cutout:
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person))
            cutout.assert_not_called()
            with Image.open(out / 'player.png') as im:
                player = im.copy()
            with Image.open(out / 'background.png') as im:
                background = im.copy()
            self.assertEqual(player.size, pl.SIZE)
            self.assertEqual(background.size, pl.SIZE)
            self.assertEqual(player.getpixel((543, 724))[:3], (255, 0, 0))
            self.assertEqual(player.getpixel((10, 10))[3], 0)
            self.assertEqual(json.loads((out / 'manifest.json').read_text())['source'], 'upload')

    def test_single_photo_is_cut_out_and_stays_on_fixed_background(self):
        bg = Image.new('RGB', (900, 1200), (0, 0, 255))
        # Un frame dello sfondo in ingresso viene ignorato: lo sfondo e' sempre fermo.
        frame = {'x': 0.1, 'zoom': 1.5}
        with tempfile.TemporaryDirectory() as tmp, patch.object(pl, 'cutout', side_effect=lambda im: im) as cutout:
            out = pl.build_layers(Path(tmp), background=png(bg), background_frame=frame)
            cutout.assert_called_once()
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['background_frame'], pl.FIXED_FRAME)
            self.assertEqual(manifest['person_frame'], pl.FIXED_FRAME)
            self.assertFalse(manifest['person_uploaded'])
            self.assertFalse(manifest['person_removed_from_background'])

    def test_moved_person_is_erased_from_background(self):
        # Sfondo verde con un rettangolo rosso (la "persona"): spostata, il rosso sparisce dallo sfondo.
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        bg.paste((255, 0, 0), (250, 300, 350, 500))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (250, 300, 350, 500))
        fill = lambda rgb, mask: __import__('numpy').full_like(rgb, (0, 128, 0))
        with tempfile.TemporaryDirectory() as tmp, patch.object(pl, '_clean_cache', {}), \
                patch('livescore.graphics.inpaint._lama', return_value=None), \
                patch('livescore.graphics.inpaint._fallback', side_effect=fill):
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person), remove_person=True,
                                  person_frame={'x': 0.25, 'y': 0.1, 'zoom': 1})
            with Image.open(out / 'background.png') as im:
                background = im.copy()
            with Image.open(out / 'player.png') as im:
                player = im.copy()
            self.assertEqual(background.getpixel((543, 724))[:3], (0, 128, 0))   # vecchia posizione ripulita
            self.assertEqual(background.getpixel((20, 20))[:3], (0, 128, 0))
            self.assertEqual(player.getpixel((543 + 271, 724 + 145))[:3], (255, 0, 0))
            self.assertTrue(json.loads((out / 'manifest.json').read_text())['person_removed_from_background'])

    def test_people_behind_are_erased_too(self):
        # Una seconda persona (blu) che lo scontorno non ha preso: sparisce dallo sfondo se la persona si sposta.
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        bg.paste((255, 0, 0), (250, 300, 350, 500))
        bg.paste((0, 0, 255), (20, 20, 120, 220))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (250, 300, 350, 500))
        everyone = Image.new('L', (600, 800))
        everyone.paste(255, (20, 20, 120, 220))
        fill = lambda rgb, mask: __import__('numpy').full_like(rgb, (0, 128, 0))
        with tempfile.TemporaryDirectory() as tmp, patch.object(pl, '_clean_cache', {}), \
                patch.object(pl, 'people_mask', return_value=everyone), \
                patch('livescore.graphics.inpaint._lama', return_value=None), \
                patch('livescore.graphics.inpaint._fallback', side_effect=fill):
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person), remove_person=True,
                                  person_frame={'x': 0.2, 'y': 0, 'zoom': 1})
            with Image.open(out / 'background.png') as im:
                self.assertEqual(im.getpixel((100, 100))[:3], (0, 128, 0))

    def test_background_untouched_when_person_not_moved_or_other_photo(self):
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        bg.paste((255, 0, 0), (250, 300, 350, 500))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (250, 300, 350, 500))
        with tempfile.TemporaryDirectory() as tmp, patch.object(pl, '_clean_cache', {}), \
                patch.object(pl, 'clean_background') as clean:
            for kwargs in ({'person_frame': None, 'remove_person': True},
                           {'person_frame': {'x': 0, 'y': 0, 'zoom': 1}, 'remove_person': True},
                           {'person_frame': {'x': 0.3, 'y': 0, 'zoom': 1}, 'remove_person': False}):
                out = pl.build_layers(Path(tmp), background=png(bg), person=png(person), **kwargs)
                with Image.open(out / 'background.png') as im:
                    self.assertEqual(im.getpixel((543, 724))[:3], (255, 0, 0))
            clean.assert_not_called()

    def test_person_with_own_frame_moves_alone(self):
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (250, 350, 350, 450))
        with tempfile.TemporaryDirectory() as tmp:
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person),
                                  person_frame={'x': 0.25, 'y': 0, 'zoom': 1})
            with Image.open(out / 'player.png') as im:
                player = im.copy()
            # Centro della persona spostato di un quarto di pagina a destra.
            self.assertEqual(player.getpixel((543 + 271, 724))[:3], (255, 0, 0))
            self.assertEqual(player.getpixel((543, 724))[3], 0)
            self.assertFalse(json.loads((out / 'manifest.json').read_text())['person_follows_background'])

    def test_person_raised_above_page_bleeds_into_top_frame_only(self):
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (200, 0, 400, 300))
        with tempfile.TemporaryDirectory() as tmp:
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person),
                                  person_frame={'x': 0, 'y': -0.03, 'zoom': 1})
            with Image.open(out / 'player_top.png') as im:
                strip = im.copy()
            self.assertEqual(strip.size, (pl.SIZE[0], pl.TOP_BLEED))
            self.assertEqual(strip.getpixel((543, pl.TOP_BLEED - 2))[:3], (255, 0, 0))
            self.assertEqual(strip.getpixel((20, pl.TOP_BLEED - 2))[3], 0)      # solo in altezza
            # Persona che resta dentro la pagina: nessuna striscia.
            out = pl.build_layers(Path(tmp), background=png(bg), person=png(person),
                                  person_frame={'x': 0, 'y': 0.2, 'zoom': 1})
            self.assertFalse((out / 'player_top.png').exists())

    def test_invalid_photo(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            pl.build_layers(Path(tmp), background=b'not an image')


if __name__ == '__main__':
    unittest.main()
