"""Pure wizard state transitions, persisted between manual workflow runs."""
import copy
import math
import re
import uuid

KINDS = [('GOAL', 'goal'), ('SAVED', 'saved'), ('KICK OFF', 'kick'),
         ('HALF TIME', 'half'), ("END OF 90'", 'end_of_90'), ('FULL TIME', 'full'), ('STATS', 'stats')]
COMPETITIONS = [('Serie A', 'ita.1'), ('Coppa Italia', 'ita.coppa_italia'),
    ('Supercoppa Italiana', 'ita.super_cup'), ('Champions League', 'uefa.champions'),
    ('Europa League', 'uefa.europa'), ('Conference League', 'uefa.europa.conf'),
    ('Supercoppa UEFA', 'uefa.super_cup'), ('Mondiale per Club', 'fifa.cwc')]
STATS = ('POSSESSO', 'xG', 'TIRI', 'TIRI IN PORTA', 'CORNER', 'FALLI',
         'FUORIGIOCO', 'AMMONITI', 'ESPULSI', 'PARATE', 'PRECISIONE PASSAGGI', 'PASSAGGI')


def parse_minute(text):
    match = re.fullmatch(r'(\d{1,3})(?:\+(\d{1,2}))?', text.strip().rstrip("'’"))
    if not match or int(match[1]) > 120:
        raise ValueError('Minuto non valido. Esempi: 56 oppure 90+12.')
    return str(int(match[1])) + ('+' + str(int(match[2])) if match[2] else '')


def parse_score(text):
    match = re.fullmatch(r'\s*(\d{1,2})\s*[-:/]\s*(\d{1,2})\s*', text)
    if not match:
        raise ValueError('Scrivi il risultato casa-trasferta, ad esempio 2-1.')
    return int(match[1]), int(match[2])


def parse_stat_pair(text):
    if text.strip() == '-':
        return None
    match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?%?)\s*[-/]\s*(\d+(?:[.,]\d+)?%?)\s*', text)
    if not match:
        raise ValueError('Due valori casa-trasferta (es. 57-43, 1.72/0.95) o - per omettere.')
    values = tuple(v.replace(',', '.') for v in match.groups())
    for value in values:
        number = float(value.rstrip('%'))
        if not math.isfinite(number) or number < 0 or number > 100000:
            raise ValueError('Valore statistica fuori intervallo.')
        if '%' in value and number > 100:
            raise ValueError('Una percentuale non può superare 100.')
    return values


class Wizard:
    def __init__(self, catalog):
        self.catalog = catalog

    def steps(self, data):
        common = ['kind', 'competition', 'kit', 'side', 'opponent']
        kind = data.get('kind')
        if kind in ('goal', 'saved'):
            common += ['player', 'minute', 'pose', 'score']
        elif kind in ('half', 'full', 'end_of_90'):
            common += ['score']
            if kind == 'full':
                common += ['shootout']
        elif kind == 'stats':
            common += ['moment'] + [f'stat:{i}' for i in range(len(STATS))]
        return common + ['confirm']

    def options(self, state):
        fixed = {'kind': KINDS, 'competition': COMPETITIONS,
            'kit': [('Home', 'home'), ('Away', 'away'), ('Third', 'third')],
            'side': [('Juventus in casa', 'home'), ('Juventus in trasferta', 'away')],
            'pose': [('Braccia incrociate', 'arms_crossed'), ('Indica', 'pointing')],
            'moment': [('HALF TIME', 'HT'), ("END OF 90'", '2H_END'), ('FULL TIME', 'FT')],
            'confirm': [('Genera PNG', 'yes'), ('Ricomincia', 'restart'), ('Annulla', 'cancel')]}
        if state.get('matches'):
            return [(v['name'], v) if isinstance(v, dict) else (v, v) for v in state['matches']]
        return fixed.get(state['step'], [])

    def prompt(self, state, prefix=''):
        step = state['step']
        titles = {'kind': 'Quale grafica vuoi creare?', 'competition': 'Scegli la competizione.',
            'kit': 'Scegli il kit.', 'side': 'Dove gioca la Juventus?',
            'opponent': 'Scrivi il nome della squadra avversaria.',
            'player': 'Scrivi il nome del giocatore.' if state['data'].get('kind') == 'goal' else 'Scrivi il nome del portiere.',
            'minute': 'Minuto? Puoi scrivere anche 90+12.', 'pose': 'Scegli la posa.',
            'score': 'Risultato casa-trasferta? Esempio: 2-1.',
            'shootout': 'Rigori finali casa-trasferta? Scrivi - se non ci sono.',
            'moment': 'A quale momento si riferiscono le statistiche?', 'confirm': self.summary(state)}
        if step.startswith('stat:'):
            label = STATS[int(step.split(':')[1])]
            title = f'{label}: valori casa-trasferta? Scrivi - per omettere il dato.'
        else:
            title = titles[step]
        choices = self.options(state)
        effect = {'text': prefix + title + '\n\n/indietro · /annulla'}
        if choices:
            effect['keyboard'] = {'inline_keyboard': [[{'text': label,
                'callback_data': f"mg:{state['id']}:{state['revision']}:{i}"}]
                for i, (label, _) in enumerate(choices)]}
        return effect

    def summary(self, state):
        d = state.get('data', {})
        if not d:
            return 'Riepilogo'
        opponent = d.get('opponent', {}).get('name', '')
        teams = f'Juventus – {opponent}' if d.get('side') == 'home' else f'{opponent} – Juventus'
        lines = ['Riepilogo', d.get('kind', '').upper(), teams,
            dict((v, k) for k, v in COMPETITIONS).get(d.get('competition'), ''),
            'Kit: ' + d.get('kit', '')]
        for key, label in [('player', 'Giocatore'), ('minute', 'Minuto'), ('pose', 'Posa'),
                           ('score', 'Risultato'), ('shootout', 'Rigori'), ('moment', 'Fase')]:
            if d.get(key) is not None:
                value = d[key]
                if isinstance(value, (list, tuple)):
                    value = '-'.join(map(str, value))
                lines.append(f'{label}: {value}')
        lines += [f'{label}: {h} – {a}' for label, h, a in d.get('rows', [])]
        return '\n'.join(lines)

    def handle(self, state, update, now):
        state = copy.deepcopy(state)
        callback = update.get('callback_query') or {}
        text = str((update.get('message') or {}).get('text') or '').strip()
        command = text.split('@')[0].lower() if text.startswith('/') else ''
        if command == '/annulla':
            if state.get('status') in ('rendering', 'sending'):
                return state, [{'text': 'Generazione già in corso; attendi il risultato.'}]
            return {'status': 'cancelled'}, [{'text': 'Richiesta annullata. /grafica per ricominciare.'}]
        if command in ('/grafica', '/nuova'):
            if state.get('status') in ('ready', 'rendering', 'sending'):
                return state, [{'text': 'Sto completando la richiesta precedente.'}]
            if state.get('status') == 'uncertain':
                return state, [{'text': 'Invio precedente incerto. Controlla la chat; /reinvia per rigenerare, /annulla per chiudere.'}]
            if command == '/nuova' or state.get('status') != 'editing' or now - state.get('updated', 0) > 1800:
                state = {'id': uuid.uuid4().hex[:10], 'revision': 0, 'step': 'kind',
                         'data': {}, 'status': 'editing', 'updated': now}
            return state, [self.prompt(state)]
        if command == '/reinvia' and state.get('status') in ('uncertain', 'failed'):
            state['status'] = 'ready'
            return state, [{'text': 'Richiesta di rigenerazione confermata.'}]
        if state.get('status') != 'editing':
            return state, [{'text': 'Scrivi /grafica per iniziare.'}]
        if now - state.get('updated', 0) > 1800:
            state['status'] = 'expired'
            return state, [{'text': 'Richiesta scaduta. Scrivi /grafica.'}]
        choices = self.options(state)
        if callback:
            parts = str(callback.get('data') or '').split(':')
            if (len(parts) != 4 or parts[:3] != ['mg', state['id'], str(state['revision'])]
                    or not parts[3].isdigit() or int(parts[3]) >= len(choices)):
                return state, [{'text': 'Pulsante scaduto. Usa quelli dell’ultima domanda.'}]
            value = choices[int(parts[3])][1]
        elif choices and text.isdigit() and 1 <= int(text) <= len(choices):
            value = choices[int(text) - 1][1]
        else:
            value = text
        steps = self.steps(state['data'])
        if command == '/indietro':
            state['step'] = steps[max(0, steps.index(state['step']) - 1)]
            state.pop('matches', None)
            state['revision'] += 1
            state['updated'] = now
            return state, [self.prompt(state)]
        try:
            step, data = state['step'], state['data']
            if step in ('opponent', 'player') and not choices:
                matches = (self.catalog.teams(text) if step == 'opponent' else
                           self.catalog.players(text, goalkeeper=data['kind'] == 'saved'))
                if not matches:
                    raise ValueError('Nome non trovato nel catalogo. Prova un altro nome.')
                if len(matches) > 15:
                    raise ValueError('Troppi risultati: scrivi un nome più preciso.')
                if len(matches) > 1:
                    state['matches'] = matches
                    state['revision'] += 1
                    state['updated'] = now
                    return state, [self.prompt(state, 'Scegli il risultato corretto.\n')]
                value = matches[0]
            elif choices and value not in [v for _, v in choices]:
                raise ValueError('Usa uno dei pulsanti o il numero della scelta.')
            if step == 'confirm':
                if value == 'yes':
                    state['status'] = 'ready'
                    return state, [{'text': 'Genero il PNG originale. Attendi…'}]
                if value == 'cancel':
                    return {'status': 'cancelled'}, [{'text': 'Richiesta annullata.'}]
                return self.handle({}, {'message': {'text': '/grafica'}}, now)
            if step == 'minute':
                value = parse_minute(text)
            if step == 'score':
                value = parse_score(text)
            if step == 'shootout':
                value = None if text == '-' else parse_score(text)
                if value and value[0] == value[1]:
                    raise ValueError('I rigori finali devono avere un vincitore.')
            if step.startswith('stat:'):
                label = STATS[int(step.split(':')[1])]
                pair = parse_stat_pair(text)
                if pair and label in ('POSSESSO', 'PRECISIONE PASSAGGI'):
                    if any(float(v.rstrip('%')) > 100 for v in pair):
                        raise ValueError('Le percentuali devono essere tra 0 e 100.')
                    pair = tuple(v.rstrip('%') + '%' for v in pair)
                rows = [r for r in data.get('rows', []) if r[0] != label]
                if pair:
                    rows.append((label, *pair))
                data['rows'] = sorted(rows, key=lambda row: STATS.index(row[0]))
            else:
                data[step] = value
            state.pop('matches', None)
            steps = self.steps(data)
            state['step'] = steps[steps.index(step) + 1]
            state['revision'] += 1
            state['updated'] = now
            return state, [self.prompt(state)]
        except ValueError as exc:
            return state, [self.prompt(state, str(exc) + '\n\n')]
