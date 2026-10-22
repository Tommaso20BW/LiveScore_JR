"""Autenticazione Canva e rinnovo del refresh token."""

import base64
import os
import time

from livescore import settings
from livescore.core import http as net
from livescore.core.log import log_line


try:
    from nacl import encoding, public
except ImportError:
    log_line("DEBUG", "SETUP", "pynacl non installata; aggiornamento Secrets GitHub non disponibile")


CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')


# ==============================================================================
# GITHUB SECRETS
# ==============================================================================
def update_github_secret(secret_name: str, new_value: str):
    if not settings.GH_PAT or not settings.GITHUB_REPOSITORY:
        return False
    headers = {
        "Authorization": f"Bearer {settings.GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        pk = net.SESSION.get(f"https://api.github.com/repos/{settings.GITHUB_REPOSITORY}/actions/secrets/public-key",
                         headers=headers, timeout=10).json()
        if "key" not in pk or "key_id" not in pk:
            log_line("ERROR", "GITHUB", f"Update secret, risposta inattesa: {pk.get('message', pk)}")
            return False
        pub_key = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        r = net.SESSION.put(f"https://api.github.com/repos/{settings.GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
                        headers=headers, json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        if r.status_code in [201, 204]:
            return True
    except Exception as e:
        log_line("ERROR", "GITHUB", f"Update secret fallito: {e}")
    return False


# ==============================================================================
# CANVA
# ==============================================================================
_CANVA_ACCESS_TOKEN = None


_CANVA_ACCESS_EXPIRES_AT = 0.0


def get_valid_token():
    global CANVA_REFRESH_TOKEN, _CANVA_ACCESS_TOKEN, _CANVA_ACCESS_EXPIRES_AT
    if _CANVA_ACCESS_TOKEN and time.monotonic() < _CANVA_ACCESS_EXPIRES_AT:
        return _CANVA_ACCESS_TOKEN
    if not CANVA_REFRESH_TOKEN:
        log_line("ERROR", "CANVA", "CANVA_REFRESH_TOKEN mancante")
        return None
    try:
        log_line("DEBUG", "CANVA", "Richiesta access token tramite refresh token")
        r = net.SESSION.post("https://api.canva.com/rest/v1/oauth/token", data={
            "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
            "client_id": settings.CLIENT_ID, "client_secret": settings.CLIENT_SECRET
        }, timeout=15)
        if r.status_code == 200:
            tokens = r.json()
            if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
                # Keep the rotated token in this process too (HT then FT).
                CANVA_REFRESH_TOKEN = tokens['refresh_token']
                log_line("DEBUG", "CANVA", "Nuovo refresh token; aggiorno GitHub Secret")
                if update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"]):
                    log_line("DEBUG", "CANVA", "GitHub Secret CANVA_REFRESH_TOKEN aggiornato")
                else:
                    # Il vecchio refresh token è stato invalidato da Canva ma il
                    # nuovo NON è stato salvato: senza intervento manuale tutti i
                    # run futuri falliranno. Avviso subito su Telegram.
                    log_line("ERROR", "CANVA", "Update GitHub Secret fallito; salvare il refresh token manualmente")
            else:
                log_line("DEBUG", "CANVA", "Access token ottenuto | refresh token invariato")
            _CANVA_ACCESS_TOKEN = tokens["access_token"]
            _CANVA_ACCESS_EXPIRES_AT = time.monotonic() + max(0, float(tokens.get('expires_in', 0))-60)
            return _CANVA_ACCESS_TOKEN
        log_line("ERROR", "CANVA", f"Richiesta token fallita: {r.text}")
    except Exception as e:
        log_line("ERROR", "CANVA", f"Connessione fallita: {e}")
    return None
