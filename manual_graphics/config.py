"""Shared setup, with no service startup as an import side effect."""
import os
import requests
from .store import GistStore
from .lifecycle import GitHub
from .canva import GitMutex, TokenManager, sync_refresh_secret


def resources(env=None):
    env = os.environ if env is None else env
    required = ('GH_PAT', 'GIST_ID', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_SHA')
    if any(not env.get(name) for name in required):
        raise RuntimeError('Configurazione GitHub/Gist incompleta')
    store = GistStore(env['GH_PAT'], env['GIST_ID'])
    api = GitHub(env.get('GH_TOKEN') or env.get('SNAPSHOT_GH_TOKEN') or env['GH_PAT'], env['GITHUB_REPOSITORY'])
    secret_api = GitHub(env['GH_PAT'], env['GITHUB_REPOSITORY'])
    tokens = TokenManager(store,
        lambda: GitMutex(api, env['GITHUB_RUN_ID'], env['GITHUB_SHA']), requests.Session(),
        env.get('CANVA_CLIENT_ID'), env.get('CANVA_CLIENT_SECRET'), env.get('CANVA_REFRESH_TOKEN'),
        lambda token: sync_refresh_secret(secret_api, token))
    return store, api, tokens
