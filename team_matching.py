"""Confronto prudente e condiviso dei nomi squadra FCLogo/ESPN, senza rete."""

import html
import re
import unicodedata
from difflib import SequenceMatcher


GENERIC_TOKENS = {
    "ac", "acf", "afc", "association", "associazione", "bc", "calcio",
    "cf", "club", "de", "del", "di", "e", "fc", "fk", "football",
    "futbol", "futebol", "sc", "sk", "societa", "sport", "sportiva",
    "ss", "sv", "the",
}
# Questi termini distinguono club diversi o prime squadre da riserve/giovanili.
DISTINCTIVE_TOKENS = {
    "united", "city", "inter", "atletico", "athletic", "sporting",
    "real", "racing", "women", "w", "femminile", "b", "ii", "u19",
    "u21", "u23", "reserves", "youth", "next", "gen",
}
MIN_SCORE = 0.90
MIN_MARGIN = 0.06


def normalize_team_name(value: str) -> str:
    raw = html.unescape(str(value or "")).casefold()
    raw = "".join(c for c in unicodedata.normalize("NFKD", raw)
                  if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", raw))


def name_tokens(value: str) -> set[str]:
    return set(normalize_team_name(value).split()) - GENERIC_TOKENS


def unique_aliases(values) -> list[str]:
    result, seen = [], set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = normalize_team_name(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def name_score(left: str, right: str) -> float:
    a, b = normalize_team_name(left), normalize_team_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    at, bt = name_tokens(a), name_tokens(b)
    if not at or not bt:
        return 0.0
    if at == bt:
        return 0.99
    if (at ^ bt) & DISTINCTIVE_TOKENS:
        return 0.0
    # NEC Nijmegen: NEC coincide con le iniziali di Nijmegen Eendracht
    # Combinatie e Nijmegen e' condiviso. Una sigla da sola non basta.
    if at & bt:
        for short, long in ((a, b), (b, a)):
            words = long.split()
            initials = {"".join(w[0] for w in words),
                        "".join(w[0] for w in words if w not in GENERIC_TOKENS)}
            remaining = name_tokens(short) - name_tokens(long)
            if (len(remaining) == 1 and len(next(iter(remaining))) >= 3
                    and remaining <= initials):
                return 0.97
        if at <= bt or bt <= at:
            return 0.90 if max(map(len, at & bt)) >= 4 else 0.0
    # Solo piccoli refusi su nomi lunghi, mai fuzzy su sigle brevi.
    aa, bb = " ".join(sorted(at)), " ".join(sorted(bt))
    ratio = SequenceMatcher(None, aa, bb).ratio()
    if min(len(aa), len(bb)) >= 6 and ratio >= 0.94:
        return 0.94
    return 0.0


class TeamIndex:
    """Indice per ID e nomi; candidati fuzzy valutati solo localmente."""

    def __init__(self, teams: list[dict], id_key: str = "espn_id"):
        self.teams = [t for t in teams if isinstance(t, dict)]
        self.names = [unique_aliases([t.get("name", ""), *t.get("aliases", [])])
                      for t in self.teams]
        self.by_id: dict[str, list[int]] = {}
        self.by_name: dict[str, set[int]] = {}
        for pos, (team, names) in enumerate(zip(self.teams, self.names)):
            team_id = str(team.get(id_key, "") or "")
            if team_id:
                self.by_id.setdefault(team_id, []).append(pos)
            for name in names:
                self.by_name.setdefault(normalize_team_name(name), set()).add(pos)

    def match(self, names: list[str], team_id: str = "") -> dict | None:
        if team_id and str(team_id) in self.by_id:
            matches = self.by_id[str(team_id)]
            return self.teams[matches[0]] if len(matches) == 1 else None
        names = unique_aliases(names)
        exact = set().union(*(self.by_name.get(normalize_team_name(n), set())
                              for n in names))
        if len(exact) > 1:
            return None
        scores = sorted(
            ((1.0 if pos in exact else
              max((name_score(a, b) for a in names for b in variants), default=0), pos)
             for pos, variants in enumerate(self.names)), reverse=True,
        )
        if not scores or scores[0][0] < MIN_SCORE:
            return None
        if len(scores) > 1 and scores[0][0] - scores[1][0] < MIN_MARGIN:
            return None
        return self.teams[scores[0][1]]
