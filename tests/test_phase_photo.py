import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from livescore.graphics import phase_layers, portrait
from livescore.hooks import bot
from livescore.match import phase_photo as pp


def png(image):
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def ctx(status='1H', elapsed=10, sent=(), home='111', away='110'):
    return SimpleNamespace(
        status=status, elapsed=elapsed, state={'sent_periods': list(sent)}, data={},
        home_id=home, away_id=away, home_name_raw='Juventus', away_name_raw='Inter',
        g_home=1, g_away=0, league_slug='ita.1', league_name='Serie A',
    )


class FakeTelegram:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, data=None, files=None, timeout=None):
        method = url.rsplit('/', 1)[-1]
        self.calls.append((method, json if json is not None else data))
        return Mock(status_code=200, json=lambda: {'ok': True, 'result': {'message_id': len(self.calls)}})


def make_desk(**kwargs):
    kwargs.setdefault('bot_chat_id', '')
    desk = pp.Desk(token='t', chat_id='42', webapp_url='https://example.org/app/',
                   direct_url='http://127.0.0.1:1', http=FakeTelegram(), **kwargs)
    with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True):
        desk.update(ctx())
    return desk


class SlotTests(unittest.TestCase):
    def test_slot_for_each_phase(self):
        self.assertEqual(pp.slot_for('half'), 'half')
        self.assertEqual(pp.slot_for('end_of_90'), 'end')
        self.assertEqual(pp.slot_for('full'), 'end')
        self.assertEqual(pp.slot_for('full', extra_time=True), 'extra')
        self.assertEqual(pp.slot_for('full', shootout=(4, 3)), 'extra')
        self.assertIsNone(pp.slot_for('second'))

    def test_prompts_ten_minutes_before(self):
        desk = make_desk()
        self.assertEqual(desk.wanted_slots(ctx('1H', 34)), [])
        self.assertEqual(desk.wanted_slots(ctx('1H', 35)), ['half'])
        self.assertEqual(desk.wanted_slots(ctx('HT', 45)), ['half'])
        self.assertEqual(desk.wanted_slots(ctx('HT', 45, sent=['HT'])), [])
        self.assertEqual(desk.wanted_slots(ctx('2H', 80)), ['end'])
        self.assertEqual(desk.wanted_slots(ctx('ET', 110)), ['extra'])
        self.assertEqual(desk.wanted_slots(ctx('PEN', 120)), ['extra'])

    def test_not_active_for_other_teams_or_friendlies(self):
        desk = make_desk()
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True):
            desk.update(ctx(home='1', away='2'))
        self.assertTrue(desk.ready('half'))
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True):
            desk.update(SimpleNamespace(**{**vars(ctx()), 'league_slug': 'club.friendly',
                                           'league_name': 'Club Friendly'}))
        self.assertTrue(desk.ready('half'))


class WaitTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        patcher = patch.object(pp, '_clock', side_effect=lambda: self.now[0])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_waits_for_photo_then_gives_up(self):
        desk = make_desk()
        desk.slots['half']['prompt_id'] = 7
        with patch.object(pp, 'WAIT_SECONDS', 300):
            self.assertFalse(desk.ready('half'))
            self.assertTrue(desk.holding())
            self.now[0] += 299
            self.assertFalse(desk.ready('half'))
            self.now[0] += 2
            self.assertTrue(desk.ready('half'))
        self.assertFalse(desk.holding())
        self.assertIsNone(desk.layers_for('half'))

    def test_wait_limit_is_two_minutes_also_in_simulation(self):
        self.assertEqual(pp.WAIT_SECONDS, 120)

    def test_no_limit_when_wait_seconds_is_none(self):
        desk = make_desk()
        desk.slots['half']['prompt_id'] = 7
        with patch.object(pp, 'WAIT_SECONDS', None):
            self.assertFalse(desk.ready('half'))
            self.now[0] += 10 ** 6
            self.assertFalse(desk.ready('half'))
            desk.slots['half']['confirmed'] = {'layers': 'x', 'request': {}, 'ids': []}
            self.assertTrue(desk.ready('half'))

    def test_cutout_state_runs_in_background(self):
        import time
        desk = make_desk()
        self.assertEqual(desk.cutout_state('abc')['state'], 'error')        # mai avviato
        self.assertEqual(desk.cutout_state('abc', start=True)['state'], 'error')   # foto sconosciuta
        desk.photos['abc'] = b'x'
        with patch.object(desk, 'cutout', side_effect=lambda pid: desk.cutouts.setdefault(pid, b'png')):
            self.assertIn(desk.cutout_state('abc', start=True)['state'], ('running', 'ready'))
            for _ in range(50):
                if desk.cutout_state('abc')['state'] == 'ready':
                    break
                time.sleep(0.02)
        self.assertEqual(desk.cutout_state('abc')['state'], 'ready')

    def test_extra_time_falls_back_to_last_confirmed_photo(self):
        desk = make_desk()
        desk.slots['end']['confirmed'] = {'layers': 'end-layers', 'request': {}, 'ids': []}
        self.assertEqual(desk.layers_for('end_of_90'), Path('end-layers'))
        self.assertEqual(desk.layers_for('full', extra_time=True), Path('end-layers'))


class RequestTests(unittest.TestCase):
    def test_parse_photo_request(self):
        envelope = {'session': 's', 'data': {'photo_id': 'a' * 16, 'frame': {'x': 9, 'zoom': 0.1},
                                             'person_frame': {'zoom': 0.1}}}
        out = pp.parse_photo_request(envelope, 's')
        # Lo sfondo e' sempre fermo: la posizione che arriva dal client viene ignorata.
        self.assertEqual(out['frame'], {'x': 0.0, 'y': 0.0, 'zoom': 1.0})
        self.assertEqual(out['person_frame']['zoom'], 0.2)
        self.assertIsNone(out['person_id'])
        with self.assertRaises(ValueError):
            pp.parse_photo_request(envelope, 'other')
        with self.assertRaises(ValueError):
            pp.parse_photo_request({'session': 's', 'data': {'photo_id': 'x'}}, 's')


class ServerTests(unittest.TestCase):
    """Mini App -> server locale: carica, conferma, la fase usa quella foto."""

    def test_upload_confirm_and_layers(self):
        desk = make_desk()
        desk.direct_url = ''
        bg = Image.new('RGB', (600, 800), (0, 128, 0))
        person = Image.new('RGBA', (600, 800))
        person.paste((255, 0, 0, 255), (200, 200, 400, 600))
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(pp, 'CACHE_DIR', Path(tmp)), \
                patch.object(pp, '_warm_up_cutout'), \
                patch.object(desk, '_open_tunnel', return_value='http://tunnel'), \
                patch.object(phase_layers, 'cutout', side_effect=lambda image: image) as cut, \
                patch.object(portrait, 'phase', return_value=png(Image.new('RGB', (10, 10)))) as render:
            desk.start()
            try:
                base = f'http://127.0.0.1:{desk.server.server_address[1]}'

                def post(path, body, content_type='application/json'):
                    request = urllib.request.Request(base + path, data=body, headers={
                        'Content-Type': content_type, 'X-ImageGEN-Session': desk.session})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        return response.read()

                photo_id = json.loads(post('/upload', png(bg), 'image/png'))['photo_id']
                person_id = json.loads(post('/upload', png(person), 'image/png'))['photo_id']
                envelope = {'v': 1, 'action': 'render', 'session': desk.session, 'data': {
                    'slot': 'half', 'kind': 'half', 'photo_id': photo_id, 'frame': {'x': 0, 'y': 0, 'zoom': 1},
                    'person_id': person_id, 'person_frame': {'x': 0.1, 'y': 0, 'zoom': 0.8}}}
                self.assertTrue(post('/preview', json.dumps(envelope).encode()).startswith(b'\x89PNG'))
                desk.slots['half']['messages'] = [7, 8]   # avviso e promemoria
                desk.messages = [7, 8]
                self.assertEqual(json.loads(post('/submit', json.dumps(envelope).encode())), {'ok': True})
                deleted = [body['message_id'] for method, body in desk.http.calls if method == 'deleteMessage']
                self.assertEqual(deleted, [])              # confermata: avvisi e pulsante restano
                edited = [body['message_id'] for method, body in desk.http.calls if method == 'editMessageText']
                self.assertEqual(edited, [7, 8])
                self.assertEqual(desk.messages, [7, 8])
                cut.assert_not_called()   # persona gia' scontornata (PNG trasparente): resta com'e'

                with urllib.request.urlopen(f'{base}/phase?session={desk.session}&slot=half') as response:
                    info = json.loads(response.read())
                self.assertEqual(info['state']['person']['id'], person_id)
                self.assertFalse(info['state']['person']['follow'])

                self.assertTrue(desk.ready('half'))
                layers = desk.layers_for('half')
                self.assertTrue((layers / 'player.png').is_file())
                self.assertTrue((layers / 'background.png').is_file())
                self.assertEqual(render.call_args.kwargs['kind'], 'half')
                self.assertIn('mode=live', desk.launch_url('half'))
                self.assertIn('direct=http%3A%2F%2Ftunnel%2Fsubmit', desk.launch_url('half'))
            finally:
                desk.server.shutdown()
                desk.server = None


class BotJrCopyTests(unittest.TestCase):
    """Copia su Bot JR: subito alla conferma, aggiornata fino al fischio, cancellata a fine partita."""

    def make(self):
        desk = make_desk(bot_chat_id='99')
        desk.slots['half']['confirmed'] = {'layers': 'L', 'request': {}, 'ids': []}
        desk.slots['half']['messages'] = [7]
        desk.messages = [7]
        return desk

    def calls(self, desk, method):
        return [body for m, body in desk.http.calls if m == method]

    def test_copy_sent_then_edited_on_score_change_then_deleted(self):
        desk = self.make()
        with patch.object(desk, '_draw', return_value=b'png'):
            desk._sync_copy('half', True)
            sent = self.calls(desk, 'sendPhoto')
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]['chat_id'], '99')
            copy_id = desk.slots['half']['copy_id']
            self.assertIsNotNone(copy_id)

            desk._sync_copy('half', False)                 # stesso risultato: niente
            self.assertEqual(len(self.calls(desk, 'editMessageMedia')), 0)

            desk.match['home_goals'] = 2                   # cambia il risultato
            desk._refresh_copies()
            for thread in __import__('threading').enumerate():
                if thread.name == 'photo-copy-half':
                    thread.join(5)
            edits = self.calls(desk, 'editMessageMedia')
            self.assertEqual(len(edits), 1)
            self.assertEqual(edits[0]['message_id'], copy_id)
            self.assertEqual(len(self.calls(desk, 'sendPhoto')), 1)   # nessun nuovo messaggio

        desk.finish()
        deleted = [b for b in self.calls(desk, 'deleteMessage') if b['chat_id'] == '99']
        self.assertEqual([b['message_id'] for b in deleted], [copy_id])

    def test_no_copy_without_bot_chat(self):
        desk = make_desk(bot_chat_id='')
        desk.slots['half']['confirmed'] = {'layers': 'L', 'request': {}, 'ids': []}
        with patch.object(desk, '_draw', return_value=b'png') as draw:
            desk._sync_copy('half', True)
        draw.assert_not_called()
        self.assertEqual(desk.http.calls, [])

    def test_published_phase_freezes_editor(self):
        desk = self.make()
        with patch.object(desk, '_draw', return_value=b'png'):
            desk._sync_copy('half', True)
            desk.slots['half']['used'] = True
            desk._phase_published('half')
        self.assertEqual([b['message_id'] for b in self.calls(desk, 'deleteMessage')], [7])
        desk.match['home_goals'] = 5
        desk._refresh_copies()                             # pubblicata: non si tocca piu'
        self.assertEqual(len(self.calls(desk, 'editMessageMedia')), 0)


@contextlib.contextmanager
def kit_runtime_off():
    """Il gestore dei kit (se un altro test l'ha installato) qui non registra nulla."""
    runner = sys.modules.get('livescore.runner')
    if runner is None:
        yield
        return
    with patch.object(runner.KIT_RUNTIME, 'enabled', False):
        yield


class BuildPhaseGraphicTests(unittest.TestCase):
    def setUp(self):
        context = kit_runtime_off()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    common = dict(data_espn={}, home_id='111', away_id='110', home_name='Juventus',
                  away_name='Inter', league_slug='ita.1', league_name='Serie A')

    def test_uses_confirmed_layers(self):
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
                patch.object(bot, 'rileva_kit_juve', return_value='home'), \
                patch.object(pp, 'layers_for', return_value=Path('confirmed')) as layers, \
                patch.object(portrait, 'phase', return_value=b'png') as render:
            self.assertEqual(bot.build_phase_graphic(kind='full', extra_time=True, **self.common), b'png')
            self.assertEqual(render.call_args.kwargs['layers'], Path('confirmed'))
            self.assertTrue(render.call_args.kwargs['extra_time'])
            self.assertTrue(layers.call_args.kwargs['extra_time'])

    def test_without_photo_sends_text(self):
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
                patch.object(pp, 'layers_for', return_value=None), \
                patch.object(portrait, 'phase') as render:
            self.assertIsNone(bot.build_phase_graphic(kind='half', **self.common))
            render.assert_not_called()

    def test_unsupported_phases_and_friendlies_have_no_graphic(self):
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True),                 patch.object(pp, 'layers_for') as layers:
            for kind in ('second_half', 'extra_time', 'penalties'):
                self.assertIsNone(bot.build_phase_graphic(kind=kind, **self.common))
            self.assertIsNone(bot.build_phase_graphic(kind='full', **{**self.common, 'league_slug': 'club.friendly'}))
            layers.assert_not_called()

    def test_second_half_needs_no_photo(self):
        with patch.object(bot, 'GOAL_GRAPHICS_ENABLED', True), \
                patch.object(bot, 'rileva_kit_juve', return_value='home'), \
                patch.object(pp, 'layers_for') as layers, \
                patch.object(portrait, 'phase', return_value=b'png') as render:
            self.assertEqual(bot.build_phase_graphic(kind='second', **self.common), b'png')
            layers.assert_not_called()
            self.assertIsNone(render.call_args.kwargs['layers'])


class SimulationClockTests(unittest.TestCase):
    def test_replay_clock_stops_while_waiting_for_photo(self):
        from livescore import simulate
        clock = simulate.FakeClock()
        clock.sleep(60)
        self.assertEqual(clock.offset, 60)
        clock.hold = lambda: True
        with patch.object(simulate, 'REAL_SLEEP') as real_sleep:
            before = clock.monotonic()
            clock.sleep(60)
            real_sleep.assert_called_once()
            self.assertAlmostEqual(clock.monotonic(), before, delta=0.05)
        clock.hold = lambda: False
        clock.sleep(30)
        self.assertGreaterEqual(clock.offset, 89.9)


if __name__ == '__main__':
    unittest.main()
