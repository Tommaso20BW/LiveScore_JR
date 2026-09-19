"""Read existing catalogs; no invented ESPN IDs or duplicated asset files."""
import json
from pathlib import Path
import goal_graphics as g


class Catalog:
    def __init__(self, assets=g.DEFAULT_ASSET_DIR):
        self.assets = Path(assets)

    def teams(self, query):
        path = self.assets / 'team_logos/fclogo_cache/manifest.json'
        rows = json.loads(path.read_text(encoding='utf-8')).get('teams', [])
        q = g.normalize_name(query)
        matches, exact = [], []
        for row in rows:
            if 'juventus' in g.normalize_name(row['name']):
                continue
            names = [g.normalize_name(n) for n in [row['name'], *row.get('aliases', [])]]
            value = {'name': row['name'], 'id': str(row.get('espn_id') or '')}
            if q and any(q in n for n in names):
                matches.append(value)
            if q in names:
                exact.append(value)
        return exact or matches

    def players(self, query, goalkeeper=False):
        q = g.normalize_name(query)
        matches, exact = [], []
        for player in g.load_players():
            if goalkeeper and player.role != 'goalkeeper':
                continue
            names = [g.normalize_name(n) for n in [player.name, *player.aliases]]
            if q and any(q in n for n in names):
                matches.append(player.name)
            if q in names:
                exact.append(player.name)
        return exact or matches
