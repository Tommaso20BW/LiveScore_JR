import io
import unittest
from unittest.mock import patch, Mock
from PIL import Image
from manual_graphics.render import Renderer, teams


class RenderTests(unittest.TestCase):
    def data(self, kind='kick'):
        return dict(kind=kind, competition='ita.1', kit='home', side='away',
                    opponent={'name': 'Inter', 'id': '110'}, score=[2, 1],
                    player='Kenan Yildiz', minute='90+12', pose='arms_crossed')

    def test_away_order(self):
        value = teams(self.data())
        self.assertEqual(value, {'home_name': 'Inter', 'home_id': '110', 'away_name': 'Juventus', 'away_id': '111'})

    def test_kick_does_not_call_canva(self):
        token = Mock(side_effect=AssertionError('No Canva for kick'))
        with patch('portrait_graphics.phase', return_value=b'png') as phase:
            self.assertEqual(Renderer(token).render(self.data()), b'png')
        self.assertIsNone(phase.call_args.kwargs['layers'])

    def test_each_phase_exports_new_page(self):
        with patch('canva_page_one.export_page_one', return_value='layers') as export, \
             patch('portrait_graphics.phase', return_value=b'png'):
            renderer = Renderer(lambda: 'token')
            renderer.render(self.data('half'))
            renderer.render(self.data('full'))
            self.assertEqual(export.call_count, 2)

    def test_real_kick_png(self):
        png = Renderer(lambda: None).render(self.data())
        with Image.open(io.BytesIO(png)) as image:
            self.assertEqual(image.size, (1086, 1448))
            self.assertEqual(image.format, 'PNG')
