"""Sessione HTTP condivisa con retry sui GET."""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ── Sessione HTTP condivisa ───────────────────────────────────────────────────
# Retry automatici SOLO sui GET (idempotenti): i POST Telegram non vengono
# ritentati in automatico per evitare doppi invii; il rate limit 429 di
# Telegram è gestito manualmente in _tg_post().
SESSION = requests.Session()


_retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)


SESSION.mount("https://", HTTPAdapter(max_retries=_retry, pool_maxsize=10))
