"""Risoluzione prudente dei loghi squadra pubblicati da Diretta.it."""

from __future__ import annotations

import base64
import html
from typing import Iterable

from team_matching import TeamIndex, unique_aliases


SEARCH_URL = "https://s.livesport.services/api/v2/search/"
IMAGE_BASE_URL = "https://static.flashscore.com/res/image/data/"
SEARCH_PARAMS = {
    "lang-id": 6,
    "type-ids": 2,
    "project-id": 400,
    "project-type-id": 1,
    "sport-ids": 1,
}
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.diretta.it/",
    "User-Agent": "Mozilla/5.0 (compatible; LiveScore_JR/1.0)",
}

# Diretta restituisce piu' formati per lo stesso stemma. Il 15 e' la
# variante 100x100 usata nella pagina della squadra; 2 e 37 sono piu' piccoli.
IMAGE_VARIANTS = (15, 2, 37)


def _clean_names(names: Iterable[str]) -> list[str]:
    return unique_aliases(html.unescape(str(name or "")) for name in names)


def _team_results(payload) -> list[dict]:
    if not isinstance(payload, list):
        return []
    return [
        item for item in payload
        if isinstance(item, dict)
        and (item.get("type") or {}).get("id") == 2
        and (item.get("sport") or {}).get("id") == 1
    ]


def _pick_team(candidates: list[dict], names: list[str]) -> dict | None:
    """Accetta soltanto un match nome univoco secondo il matcher condiviso."""
    teams = []
    for candidate in candidates:
        teams.append({
            **candidate,
            # Lo slug non e' un alias affidabile: sul sito, per esempio,
            # Juventus e Juventus U23 possono condividere ``juventus``.
            "aliases": [],
            "diretta_id": candidate.get("id", ""),
        })
    return TeamIndex(teams, id_key="diretta_id").match(names)


def _image_path(team: dict) -> str | None:
    images = [item for item in team.get("images", []) if isinstance(item, dict)]
    for variant in IMAGE_VARIANTS:
        for image in images:
            path = str(image.get("path", ""))
            if image.get("usageId") == 2 and image.get("variantTypeId") == variant and path:
                return path
    return None


def resolve_team_logo(names: Iterable[str], session, timeout: int = 10) -> tuple[str, str] | None:
    """Restituisce ``(data_uri, nome_Diretta)`` o ``None``.

    Prima individua una squadra non ambigua tramite la stessa ricerca usata dal
    sito, poi scarica il PNG: incorporarlo nell'HTML evita che Playwright debba
    completare una seconda richiesta di rete durante lo screenshot.
    """
    clean_names = _clean_names(names)
    if not clean_names:
        return None

    candidates: dict[str, dict] = {}
    for query in clean_names:
        response = session.get(
            SEARCH_URL,
            params={**SEARCH_PARAMS, "q": query},
            headers=HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        for item in _team_results(response.json()):
            item_id = str(item.get("id", ""))
            if item_id:
                candidates.setdefault(item_id, item)
        picked = _pick_team(list(candidates.values()), clean_names)
        if picked is not None:
            break
    else:
        picked = _pick_team(list(candidates.values()), clean_names)

    if picked is None:
        return None
    path = _image_path(picked)
    if path is None:
        return None

    image_response = session.get(
        IMAGE_BASE_URL + path,
        headers=HEADERS,
        timeout=timeout,
    )
    image_response.raise_for_status()
    content = image_response.content
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/png;base64,{encoded}", str(picked.get("name", ""))
