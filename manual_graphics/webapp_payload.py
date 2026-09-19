"""Validate requests received from the Telegram Keyboard Button Mini App."""
import json
import math
import uuid

from .conversation import COMPETITIONS, KINDS, STATS, parse_minute, parse_stat_pair


VALID_KINDS = {value for _, value in KINDS}
VALID_COMPETITIONS = {value for _, value in COMPETITIONS}
VALID_KITS = {'home', 'away', 'third'}
VALID_SIDES = {'home', 'away'}
VALID_POSES = {'arms_crossed', 'pointing'}
VALID_MOMENTS = {'HT', '2H_END', 'FT'}
BUSY = {'ready', 'rendering', 'sending'}


def _score(value, *, optional=False, shootout=False):
    if value in (None, '', []):
        if optional:
            return None
        raise ValueError('Risultato mancante.')
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError('Risultato non valido.')
    try:
        home, away = int(value[0]), int(value[1])
    except (TypeError, ValueError):
        raise ValueError('Risultato non valido.') from None
    if not (0 <= home <= 99 and 0 <= away <= 99):
        raise ValueError('Risultato fuori intervallo.')
    if shootout and home == away:
        raise ValueError('I rigori devono avere un vincitore.')
    return home, away


def _canonical_team(catalog, value):
    if not isinstance(value, dict):
        raise ValueError('Avversario non valido.')
    name = str(value.get('name') or '').strip()
    if not name:
        raise ValueError('Avversario mancante.')
    matches = catalog.teams(name)
    if not matches:
        raise ValueError('Avversario non presente nel catalogo.')
    exact = [row for row in matches if row['name'].casefold() == name.casefold()]
    return exact[0] if exact else matches[0]


def _canonical_player(catalog, value, *, goalkeeper=False):
    name = str(value or '').strip()
    if not name:
        raise ValueError('Giocatore mancante.')
    matches = catalog.players(name, goalkeeper=goalkeeper)
    if not matches:
        raise ValueError('Giocatore non presente nel catalogo.')
    exact = [candidate for candidate in matches if candidate.casefold() == name.casefold()]
    if exact:
        return exact[0]
    if len(matches) == 1:
        return matches[0]
    raise ValueError('Giocatore ambiguo: selezionalo dall’elenco.')


def _rows(value):
    if not isinstance(value, list):
        return []
    rows, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('Statistiche non valide.')
        label = str(item.get('label') or '').strip()
        if label not in STATS or label in seen:
            raise ValueError('Statistica non valida.')
        home = str(item.get('home') or '').strip()
        away = str(item.get('away') or '').strip()
        if not home and not away:
            continue
        if not home or not away:
            raise ValueError(f'{label}: inserisci entrambi i valori.')
        pair = parse_stat_pair(f'{home}/{away}')
        if not pair:
            continue
        if label in ('POSSESSO', 'PRECISIONE PASSAGGI'):
            if any(float(v.rstrip('%')) > 100 for v in pair):
                raise ValueError(f'{label}: percentuale oltre 100.')
            pair = tuple(v.rstrip('%') + '%' for v in pair)
        for cell in pair:
            number = float(cell.rstrip('%'))
            if not math.isfinite(number):
                raise ValueError('Statistica non valida.')
        rows.append((label, pair[0], pair[1]))
        seen.add(label)
    return sorted(rows, key=lambda row: STATS.index(row[0]))


def parse_webapp_update(state, update, catalog, now, expected_session=None):
    """Return (new_state, effects) for a Telegram web_app_data update."""
    if state.get('status') in BUSY:
        return state, [{'text': 'Sto già generando una grafica. Attendi il PNG prima di inviarne un’altra.'}]

    try:
        message = update.get('message') or {}
        raw = str((message.get('web_app_data') or {}).get('data') or '')
        if not raw or len(raw.encode('utf-8')) > 4096:
            raise ValueError('Dati Mini App mancanti o troppo lunghi.')
        envelope = json.loads(raw)
        # The workflow creates a fresh session token for every 30-minute run.
        # Stale Mini App submissions from an older run are silently discarded.
        if expected_session and str(envelope.get('session') or '') != str(expected_session):
            return state, []
        if envelope.get('v') != 1 or envelope.get('action') != 'render':
            raise ValueError('Versione Mini App non supportata.')
        incoming = envelope.get('data')
        if not isinstance(incoming, dict):
            raise ValueError('Richiesta non valida.')

        kind = str(incoming.get('kind') or '')
        competition = str(incoming.get('competition') or '')
        kit = str(incoming.get('kit') or '')
        side = str(incoming.get('side') or '')
        if kind not in VALID_KINDS:
            raise ValueError('Tipo grafica non valido.')
        if competition not in VALID_COMPETITIONS:
            raise ValueError('Competizione non valida.')
        if kit not in VALID_KITS:
            raise ValueError('Kit non valido.')
        if side not in VALID_SIDES:
            raise ValueError('Casa/trasferta non valido.')

        data = {
            'kind': kind,
            'competition': competition,
            'kit': kit,
            'side': side,
            'opponent': _canonical_team(catalog, incoming.get('opponent')),
        }

        if kind in ('goal', 'saved'):
            data['player'] = _canonical_player(
                catalog, incoming.get('player'), goalkeeper=(kind == 'saved'))
            data['minute'] = parse_minute(str(incoming.get('minute') or ''))
            pose = str(incoming.get('pose') or '')
            if pose not in VALID_POSES:
                raise ValueError('Posa non valida.')
            data['pose'] = pose
            data['score'] = _score(incoming.get('score'))
        elif kind in ('half', 'full', 'end_of_90'):
            data['score'] = _score(incoming.get('score'))
            if kind == 'full':
                data['shootout'] = _score(
                    incoming.get('shootout'), optional=True, shootout=True)
        elif kind == 'stats':
            moment = str(incoming.get('moment') or '')
            if moment not in VALID_MOMENTS:
                raise ValueError('Momento statistiche non valido.')
            data['moment'] = moment
            data['rows'] = _rows(incoming.get('rows'))
            if not data['rows']:
                raise ValueError('Inserisci almeno una statistica.')

        return {
            'id': uuid.uuid4().hex[:10],
            'revision': 0,
            'data': data,
            'status': 'ready',
            'updated': now,
            'source': 'webapp',
        }, []
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return state, [{'text': f'Mini App: {exc}'}]
