import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import canva_page_one as canva
import juve_bot_espn as bot

class CanvaExportTests(unittest.TestCase):
    def test_pdf_page_one_only(self):
        session = Mock()
        session.post.return_value.json.return_value = {'job': {'id': 'test'}}
        session.get.side_effect = [Mock(json=lambda: {'job': {'status':'success','urls':['https://example.test/pdf']}}),Mock(content=b'pdf')]
        with tempfile.TemporaryDirectory() as root, patch.object(canva,'extract_layers',return_value=Path(root)) as extract:
            canva.export_page_one(session,'token','design',Path(root),sleep=lambda _: None)
            extract.assert_called_once()
        self.assertEqual(session.post.call_args.kwargs['json']['format'],{'type':'pdf','pages':[1]})

    def test_failure_without_cache_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                canva.export_page_one(Mock(),'','design',Path(root))

    def test_offline_reuses_validated_cache(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); folder=root/'abc'; folder.mkdir()
            for name in ('player.png','background.png','manifest.json'): (folder/name).touch()
            (root/'current.json').write_text('{"folder":"abc"}')
            self.assertEqual(canva.export_page_one(Mock(),'','design',root),folder)

    def test_legacy_kit_pages_removed(self):
        self.assertFalse(hasattr(bot,'PAGINA_PER_KIT'))
        self.assertFalse(hasattr(bot,'get_canva_image'))

    def test_unsupported_phases_and_friendlies_do_not_export(self):
        common=dict(data_espn={},home_id='111',away_id='110',home_name='Juventus',away_name='Inter',league_slug='ita.1',league_name='Serie A')
        with patch.object(bot,'GOAL_GRAPHICS_ENABLED',True), patch.object(bot,'get_valid_token') as token:
            for kind in ('second_half','extra_time','penalties'):
                self.assertIsNone(bot.build_phase_graphic(kind=kind,**common))
            common['league_slug']='club.friendly'
            self.assertIsNone(bot.build_phase_graphic(kind='full',**common))
            token.assert_not_called()

if __name__ == '__main__': unittest.main()
