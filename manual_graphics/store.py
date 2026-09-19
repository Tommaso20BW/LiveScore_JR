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
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def http_error(response, operation, filename):
    # Whitelist numeric metadata only; never log URLs, headers or response bodies.
    retry = str(response.headers.get('Retry-After', ''))
    delay = int(retry) if retry.isdigit() else 0
    if response.status_code in (403, 429):
        delay = max(60, delay)
    elif response.status_code >= 500:
        delay = max(15, delay)
    return StorageError(f'Gist {operation} {filename}: HTTP {response.status_code}', delay)


class GistStore:
    def __init__(self, token, gist_id, session=None):
        if not token or not gist_id:
            raise StorageError('GH_PAT e GIST_ID necessari')
        self.url = f'https://api.github.com/gists/{gist_id}'
        self.session = session or requests.Session()
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
        self.lock = threading.RLock()
        self._verified = False

    def _get(self, filename='metadata'):
        try:
            r = self.session.get(self.url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                raise http_error(r, 'GET', filename)
            data = r.json()
            if data.get('public') is not False:
                raise StorageError('Richiesto Gist non pubblico per lo stato riservato')
            self._verified = True
            return data
        except requests.RequestException:
            raise StorageError(f'Gist GET {filename}: rete non disponibile', 15) from None

    def read(self, name):
        with self.lock:
            item = self._get(FILES[name]).get('files', {}).get(FILES[name], {})
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
                    raise http_error(r, 'PATCH', FILES[name])
            except requests.RequestException:
                raise StorageError(f'Gist PATCH {FILES[name]}: salvataggio non confermato', 15) from None
