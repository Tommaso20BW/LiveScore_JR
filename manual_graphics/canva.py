"""Shared rotating Canva credentials, serialized only while refreshing.

The Git reference holds public-safe lock metadata only. Credentials stay in
the private Gist. Fast-forward updates provide compare-and-swap arbitration.
"""
import base64
import json
import threading
import time
import requests


class GitMutex:
    REF = 'heads/jr-manual-canva-lock'

    def __init__(self, api, run_id, base_sha, wait_seconds=45, attempt=1):
        self.api, self.run_id, self.base_sha = api, str(run_id), base_sha
        self.wait_seconds = wait_seconds
        self.held = None
        self.attempt = int(attempt)

    def _commit(self, parent, tree, locked):
        return self.api.json('POST', 'git/commits', json={
            'message': json.dumps({'jr_manual_canva_lock': True, 'locked': locked,
                                   'run_id': self.run_id, 'attempt': self.attempt}),
            'tree': tree, 'parents': [parent]})['sha']

    def _head(self):
        r = self.api.request('GET', f'git/ref/{self.REF}')
        if r.status_code == 404:
            base = self.api.json('GET', f'git/commits/{self.base_sha}')
            sha = self._commit(self.base_sha, base['tree']['sha'], False)
            created = self.api.request('POST', 'git/refs', json={'ref': 'refs/' + self.REF, 'sha': sha})
            if created.status_code not in (201, 422):
                raise RuntimeError('Impossibile inizializzare lock Canva')
            r = self.api.request('GET', f'git/ref/{self.REF}')
        if r.status_code != 200:
            raise RuntimeError('Lock Canva non leggibile')
        sha = r.json()['object']['sha']
        commit = self.api.json('GET', f'git/commits/{sha}')
        state = json.loads(commit['message'])
        if not state.get('jr_manual_canva_lock'):
            raise RuntimeError('Branch lock Canva non riconosciuto')
        return sha, commit['tree']['sha'], state

    def _advance(self, parent, tree, locked):
        sha = self._commit(parent, tree, locked)
        response = self.api.request('PATCH', f'git/refs/{self.REF}', json={'sha': sha, 'force': False})
        if response.status_code == 200:
            return sha
        if response.status_code in (409, 422):
            return None
        raise RuntimeError('Aggiornamento lock Canva fallito')

    def __enter__(self):
        deadline = time.monotonic() + self.wait_seconds
        while time.monotonic() < deadline:
            sha, tree, state = self._head()
            if not state.get('locked') or not self.api.run_active(
                    state['run_id'], attempt=state.get('attempt', 1)):
                self.held = self._advance(sha, tree, True)
                if self.held:
                    return self
            time.sleep(2)
        raise RuntimeError('Canva occupato: riprova tra poco')

    def __exit__(self, *args):
        sha, tree, _ = self._head()
        if sha == self.held:
            if not self._advance(sha, tree, False):
                raise RuntimeError('Rilascio lock Canva non confermato')
        self.held = None


class TokenManager:
    def __init__(self, store, mutex_factory, session, client_id, client_secret, refresh_token, sync_secret):
        self.store, self.mutex_factory, self.session = store, mutex_factory, session
        self.client_id, self.client_secret = client_id, client_secret
        self.refresh_token, self.sync_secret = refresh_token, sync_secret
        self.local_lock = threading.Lock()
        self.pending = None

    def get(self, now=None):
        now = time.time() if now is None else now
        with self.local_lock:
            cached = self.store.read('canva')
            if (not self.pending and cached.get('access_token')
                    and float(cached.get('expires_at', 0)) > now
                    and cached.get('secret_synced', True)):
                return cached['access_token']
            with self.mutex_factory():
                # If a save failed after OAuth rotation, retry that exact token,
                # never another refresh with the old startup environment.
                if self.pending:
                    self.store.write('canva', self.pending)
                    self.pending = None
                state = self.store.read('canva')
                if state.get('access_token') and float(state.get('expires_at', 0)) > now:
                    if not state.get('secret_synced', True) and state.get('refresh_token'):
                        state['secret_synced'] = bool(self.sync_secret(state['refresh_token']))
                        self.store.write('canva', state)
                    return state['access_token']
                refresh = state.get('refresh_token') or self.refresh_token
                if not refresh or not self.client_id or not self.client_secret:
                    raise RuntimeError('Credenziali Canva mancanti')
                try:
                    response = self.session.post('https://api.canva.com/rest/v1/oauth/token', data={
                        'grant_type': 'refresh_token', 'refresh_token': refresh,
                        'client_id': self.client_id, 'client_secret': self.client_secret}, timeout=20)
                except requests.RequestException:
                    raise RuntimeError('Connessione OAuth Canva non disponibile') from None
                if response.status_code != 200:
                    raise RuntimeError(f'OAuth Canva HTTP {response.status_code}')
                tokens = response.json()
                new_state = {'access_token': tokens['access_token'],
                    'refresh_token': tokens.get('refresh_token') or refresh,
                    'expires_at': now + max(0, float(tokens.get('expires_in', 0)) - 60),
                    'secret_synced': False}
                self.pending = new_state
                self.refresh_token = new_state['refresh_token']
                self.store.write('canva', new_state)
                self.pending = None
                new_state['secret_synced'] = bool(self.sync_secret(new_state['refresh_token']))
                self.store.write('canva', new_state)
                return new_state['access_token']


def sync_refresh_secret(api, token):
    from nacl import public, encoding
    try:
        key = api.json('GET', 'actions/secrets/public-key')
        public_key = public.PublicKey(key['key'].encode(), encoding.Base64Encoder())
        encrypted = public.SealedBox(public_key).encrypt(token.encode())
        api.json('PUT', 'actions/secrets/CANVA_REFRESH_TOKEN', json={
            'key_id': key['key_id'], 'encrypted_value': base64.b64encode(encrypted).decode()})
        return True
    except Exception:
        # The private Gist is authoritative even when secret synchronization fails.
        print('WARN CANVA: secret non sincronizzato; token conservato nel Gist riservato', flush=True)
        return False
