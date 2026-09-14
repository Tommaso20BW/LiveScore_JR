import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
import canva_page_one as canva
import juve_bot_espn as bot
import portrait_graphics as portrait


def seed_cache(root):
    folder = root / 'previous'
    folder.mkdir()
    for name in ('player.png', 'background.png', 'manifest.json'):
        (folder / name).touch()
    (root / 'current.json').write_text(json.dumps({'folder': folder.name}))
    return folder


def page_one_pdf(color):
    """Real embedded background and masked player, plus an unused second page."""
    import pymupdf
    with pymupdf.open() as doc:
        page = doc.new_page(width=1086, height=1448)
        for image in (Image.new('RGB', (30, 40), 'white'),
                      Image.new('RGBA', (30, 40), (*color, 180))):
            stream = io.BytesIO()
            image.save(stream, format='PNG')
            page.insert_image(page.rect, stream=stream.getvalue())
        doc.new_page().insert_text((50, 50), 'This page must not be used')
        return doc.tobytes()


def export_session(*pdfs):
    session = Mock()
    session.post.side_effect = [
        Mock(json=lambda i=i: {'job': {'id': f'export-{i}'}})
        for i in range(len(pdfs))
    ]
    session.get.side_effect = [response for i, pdf in enumerate(pdfs) for response in (
        Mock(json=lambda i=i: {'job': {'status': 'success',
                                      'urls': [f'https://example.test/{i}.pdf']}}),
        Mock(content=pdf),
    )]
    return session


class CanvaExportTests(unittest.TestCase):
    def test_pdf_page_one_only(self):
        session = Mock()
        session.post.return_value.json.return_value = {'job': {'id': 'test'}}
        session.get.side_effect = [
            Mock(json=lambda: {
                'job': {
                    'status': 'success',
                    'urls': ['https://example.test/pdf']
                }
            }),
            Mock(content=b'pdf')
        ]

        with tempfile.TemporaryDirectory() as root, \
             patch.object(canva, 'extract_layers', return_value=Path(root)) as extract:
            canva.export_page_one(
                session,
                'token',
                'design',
                Path(root),
                sleep=lambda _: None
            )
            extract.assert_called_once()

        self.assertEqual(
            session.post.call_args.kwargs['json']['format'],
            {
                'type': 'pdf',
                'pages': [1],
                'export_quality': 'pro',
            }
        )

    def test_failure_without_cache_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                canva.export_page_one(Mock(), '', 'design', Path(root))

    def test_missing_token_never_reuses_previous_period(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            seed_cache(root)
            session = Mock()

            with self.assertRaisesRegex(ValueError, 'Token Canva assente'):
                canva.export_page_one(session, '', 'design', root)

            session.post.assert_not_called()

    def test_consecutive_requests_download_changed_page_one_and_identical_pdf(self):
        first_pdf = page_one_pdf((255, 0, 0))
        second_pdf = page_one_pdf((0, 0, 255))
        session = export_session(first_pdf, second_pdf, second_pdf)

        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            folders = [
                canva.export_page_one(
                    session,
                    'token',
                    'design',
                    root,
                    sleep=lambda _: None
                )
                for _ in range(3)
            ]

            self.assertNotEqual(folders[0], folders[1])
            self.assertEqual(folders[1], folders[2])

            for folder, color, pdf in zip(
                folders,
                [(255, 0, 0), (0, 0, 255), (0, 0, 255)],
                [first_pdf, second_pdf, second_pdf]
            ):
                with Image.open(folder / 'player.png') as player:
                    # PDF alpha premultiplication can round channels slightly.
                    for actual, expected in zip(
                        player.getpixel((500, 700))[:3],
                        color
                    ):
                        self.assertAlmostEqual(actual, expected, delta=3)

                self.assertEqual(
                    (folder / 'source.pdf').read_bytes(),
                    pdf
                )
                self.assertEqual(
                    json.loads(
                        (folder / 'manifest.json').read_text()
                    )['page'],
                    1
                )

            self.assertEqual(
                json.loads(
                    (root / 'current.json').read_text()
                )['folder'],
                folders[-1].name
            )

        self.assertEqual(session.post.call_count, 3)

        for call in session.post.call_args_list:
            self.assertEqual(
                call.kwargs['json'],
                {
                    'design_id': 'design',
                    'format': {
                        'type': 'pdf',
                        'pages': [1],
                        'export_quality': 'pro',
                    }
                }
            )

        self.assertEqual(
            [call.args[0] for call in session.get.call_args_list],
            [
                url
                for i in range(3)
                for url in (
                    f'https://api.canva.com/rest/v1/exports/export-{i}',
                    f'https://example.test/{i}.pdf'
                )
            ]
        )

    def test_failed_export_download_or_extraction_never_returns_old_layers(self):
        import pymupdf

        for stage in (
            'create',
            'poll',
            'failed_job',
            'download',
            'invalid_pdf',
            'timeout'
        ):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                old = seed_cache(root)
                session = export_session(b'invalid pdf')
                expected = OSError

                if stage == 'create':
                    session.post.side_effect = OSError('Canva unavailable')

                elif stage == 'poll':
                    session.get.side_effect = OSError('Canva unavailable')

                elif stage == 'download':
                    session.get.side_effect = [
                        Mock(json=lambda: {
                            'job': {
                                'status': 'success',
                                'urls': ['https://example.test/pdf']
                            }
                        }),
                        OSError('Download unavailable'),
                    ]

                else:
                    expected = pymupdf.FileDataError

                    if stage in ('failed_job', 'timeout'):
                        session.get.side_effect = None
                        session.get.return_value.json.return_value = {
                            'job': {
                                'status': (
                                    'failed'
                                    if stage == 'failed_job'
                                    else 'inprogress'
                                )
                            }
                        }
                        expected = (
                            ValueError
                            if stage == 'failed_job'
                            else TimeoutError
                        )

                with self.assertRaises(expected):
                    canva.export_page_one(
                        session,
                        'token',
                        'design',
                        root,
                        sleep=lambda _: None
                    )

                self.assertEqual(
                    json.loads(
                        (root / 'current.json').read_text()
                    )['folder'],
                    old.name
                )

    def test_corrupt_cache_manifest_does_not_prevent_fresh_download(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'current.json').write_text('invalid json')
            pdf = page_one_pdf((0, 255, 0))

            result = canva.export_page_one(
                export_session(pdf),
                'token',
                'design',
                root,
                sleep=lambda _: None
            )

            self.assertEqual(
                (result / 'source.pdf').read_bytes(),
                pdf
            )

    def test_legacy_kit_pages_removed(self):
        self.assertFalse(hasattr(bot, 'PAGINA_PER_KIT'))
        self.assertFalse(hasattr(bot, 'get_canva_image'))

    def test_unsupported_phases_and_friendlies_do_not_export(self):
        common = dict(
            data_espn={},
            home_id='111',
            away_id='110',
            home_name='Juventus',
            away_name='Inter',
            league_slug='ita.1',
            league_name='Serie A'
        )

        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'get_valid_token') as token:
            for kind in ('second_half', 'extra_time', 'penalties'):
                self.assertIsNone(
                    bot.build_phase_graphic(kind=kind, **common)
                )

            common['league_slug'] = 'club.friendly'
            self.assertIsNone(
                bot.build_phase_graphic(kind='full', **common)
            )
            token.assert_not_called()


class PhaseFreshnessTests(unittest.TestCase):
    common = dict(
        data_espn={},
        home_id='111',
        away_id='110',
        home_name='Juventus',
        away_name='Inter',
        league_slug='ita.1',
        league_name='Serie A'
    )

    def test_every_phase_request_including_repeated_phase_uses_new_layers(self):
        folders = [Path(f'export-{i}') for i in range(4)]

        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'get_valid_token', return_value='token'), \
             patch.object(bot, 'rileva_kit_juve', return_value='home'), \
             patch.object(canva, 'export_page_one', side_effect=folders) as export, \
             patch.object(portrait, 'phase', return_value=b'png') as render:

            for kind, folder in zip(
                ('half', 'end_of_90', 'full', 'full'),
                folders
            ):
                self.assertEqual(
                    bot.build_phase_graphic(
                        kind=kind,
                        **self.common
                    ),
                    b'png'
                )
                self.assertEqual(
                    render.call_args.kwargs['layers'],
                    folder
                )

            self.assertEqual(export.call_count, 4)

    def test_retry_after_export_failure_downloads_again_before_rendering(self):
        fresh = Path('fresh-export')

        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'get_valid_token', return_value='token'), \
             patch.object(bot, 'rileva_kit_juve', return_value='home'), \
             patch.object(
                 canva,
                 'export_page_one',
                 side_effect=[ValueError('failed'), fresh]
             ) as export, \
             patch.object(portrait, 'phase', return_value=b'new-png') as render, \
             patch.object(bot, 'send_telegram_get_id', return_value=42) as send, \
             patch.object(
                 bot,
                 'edit_telegram_goal_photo',
                 return_value=True
             ) as edit:

            self.assertEqual(
                bot.send_phase_message(
                    'Half time',
                    kind='half',
                    **self.common
                ),
                42
            )

        self.assertEqual(export.call_count, 2)
        render.assert_called_once()
        self.assertEqual(
            render.call_args.kwargs['layers'],
            fresh
        )
        send.assert_called_once_with('Half time')
        edit.assert_called_once_with(
            42,
            'Half time',
            b'new-png'
        )

    def test_persistent_export_failure_leaves_text_and_never_renders_old_image(self):
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
             patch.object(bot, 'get_valid_token', return_value='token'), \
             patch.object(
                 canva,
                 'export_page_one',
                 side_effect=ValueError('failed')
             ) as export, \
             patch.object(portrait, 'phase') as render, \
             patch.object(
                 bot,
                 'send_telegram_get_id',
                 return_value=42
             ), \
             patch.object(
                 bot,
                 'edit_telegram_goal_photo'
             ) as edit:

            self.assertEqual(
                bot.send_phase_message(
                    'Full time',
                    kind='full',
                    **self.common
                ),
                42
            )

        self.assertEqual(export.call_count, 6)
        render.assert_not_called()
        edit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
