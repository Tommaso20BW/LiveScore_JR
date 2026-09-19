"""Thin adapters to the current production renderers, with no publishing."""
from pathlib import Path
import tempfile
import requests


def teams(data):
    opponent = data['opponent']
    juve = {'name': 'Juventus', 'id': '111'}
    home, away = (juve, opponent) if data['side'] == 'home' else (opponent, juve)
    return dict(home_name=home['name'], home_id=home.get('id', ''),
                away_name=away['name'], away_id=away.get('id', ''))


class Renderer:
    def __init__(self, token_provider, design_id='DAHI3ytu6yQ'):
        self.token_provider = token_provider
        self.design_id = design_id

    def render(self, data):
        import goal_graphics as g
        import portrait_graphics as p
        from canva_page_one import export_page_one
        from manual_graphics.conversation import COMPETITIONS
        kind = data['kind']
        common = dict(**teams(data), kit=data['kit'], competition=data['competition'])
        score = data.get('score') or (0, 0)
        if kind in ('goal', 'saved'):
            args = dict(**common, minute=data['minute'], home_goals=score[0], away_goals=score[1],
                        pose=data.get('pose', 'arms_crossed'))
            if kind == 'goal':
                return g.render_goal_card(**args, scorer_name=data['player']).png
            return g.render_saved_card(**args, goalkeeper_name=data['player']).png
        if kind in ('kick', 'half', 'full', 'end_of_90'):
            with tempfile.TemporaryDirectory(prefix='jr_manual_') as cache:
                layers = None
                if kind != 'kick':
                    with requests.Session() as session:
                        layers = export_page_one(session, self.token_provider(), self.design_id, Path(cache))
                return p.phase(**common, kind=kind, home_goals=score[0], away_goals=score[1],
                               shootout=data.get('shootout') if kind == 'full' else None, layers=layers)
        if kind == 'stats':
            import stats_graphics as stats
            import shutil
            html = stats.build_html(**common, rows=data.get('rows', []), momento=data['moment'],
                league_name=dict((v, k) for k, v in COMPETITIONS)[data['competition']])
            target = Path(stats.render(html, hd_output=True))
            try:
                return target.read_bytes()
            finally:
                # Only renderer-created temporary directories, never arbitrary paths.
                if target.name == 'stats.png' and target.parent.name.startswith('jr_stats_'):
                    shutil.rmtree(target.parent)
        raise ValueError('Tipo grafica non supportato')
