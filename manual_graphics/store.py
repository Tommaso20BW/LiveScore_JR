"""Private Gist documents with explicit ownership; never rewrite live state."""
import json
import threading
import requests

FILES = {
    'receiver': 'manual_receiver.json',
    'control': 'manual_control.json',
    'ack': 'manual_live_ack.json',
    'session': 'manual_session.json',
    'canva': 'manual_canva.json',
}


class StorageError(RuntimeError):
    pass


class GistStore:
    def __init__(self, token, gist_id, session=None):
        if not token or not gist_id:
            raise StorageError('GH_PAT e GIST_ID necessari')
        self.url = f'https://api.github.com/gists/{gist_id}'
        self.session = session or requests.Session()
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
        self.lock = threading.RLock()
        self._verified = False

    def _get(self):
        try:
            r = self.session.get(self.url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                raise StorageError(f'Lettura Gist HTTP {r.status_code}')
            data = r.json()
            if data.get('public') is not False:
                raise StorageError('Richiesto Gist non pubblico per lo stato riservato')
            self._verified = True
            return data
        except requests.RequestException:
            raise StorageError('Gist non raggiungibile') from None

    def read(self, name):
        with self.lock:
            item = self._get().get('files', {}).get(FILES[name], {})
            if item.get('truncated'):
                raise StorageError('Stato Gist troppo grande; nessun avanzamento')
            try:
                value = json.loads(item.get('content') or '{}')
                if not isinstance(value, dict):
                    raise ValueError()
                return value
            except (ValueError, TypeError):
                raise StorageError('Stato Gist non valido') from None

    def write(self, name, value):
        content = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        if len(content.encode()) > 200_000:
            raise StorageError('Coda piena: stato non salvato')
        with self.lock:
            if not self._verified:
                self._get()
            try:
                r = self.session.patch(self.url, headers=self.headers,
                    json={'files': {FILES[name]: {'content': content}}}, timeout=15)
                if r.status_code != 200:
                    raise StorageError(f'Salvataggio Gist HTTP {r.status_code}')
            except requests.RequestException:
                raise StorageError('Salvataggio Gist non confermato') from None
