"""Correzioni manuali delle squadre (mini app ImageGen › Impostazioni › Squadre e loghi).

Vivono nel repo degli asset, FUORI da team_logos/: la sincronizzazione FCLogo
riscrive il manifest e cancella i PNG che non conosce, qui non entra mai.

    team_overrides/overrides.json
    team_overrides/logos/<file>.png

Formato di overrides.json:

    {"version": 1, "teams": {
        "<chiave>": {
            "base": "FC Inter Milan",          # squadra del catalogo FCLogo; null = squadra nuova
            "name": "Inter",                   # nome mostrato (facoltativo)
            "aliases": ["Internazionale"],     # nomi ESPN collegati in più (facoltativo)
            "tag": "Inter",                    # hashtag senza # (facoltativo)
            "logo": "logos/fc-inter-milan.png" # logo caricato a mano (facoltativo)
        }
    }}

Ogni campo si può togliere da solo: senza "logo" torna il logo FCLogo, senza
"name" il nome originale, e così via. Senza file tutto funziona come prima.
"""

from __future__ import annotations

import json
from pathlib import Path

from livescore.core.team_matching import normalize_team_name, unique_aliases
from livescore.paths import ASSETS_DIR

DIRNAME = "team_overrides"
FILENAME = "overrides.json"

_cache: dict[str, tuple[tuple, dict]] = {}


def overrides_path(asset_dir: Path | str = ASSETS_DIR) -> Path:
    return Path(asset_dir) / DIRNAME / FILENAME


def clean_entry(entry: dict) -> dict | None:
    """Voce valida (campi vuoti tolti) oppure None se non resta niente da correggere."""
    if not isinstance(entry, dict):
        return None
    base = str(entry.get("base") or "").strip() or None
    name = " ".join(str(entry.get("name") or "").split()) or None
    logo = str(entry.get("logo") or "").strip() or None
    tag = "".join(str(entry.get("tag") or "").split()).lstrip("#") or None
    aliases = unique_aliases(" ".join(str(a).split()) for a in (entry.get("aliases") or []) if str(a).strip())
    if base is None and not (name and logo):
        return None      # squadra nuova: servono nome e logo
    out = {"base": base}
    if name and name != base:
        out["name"] = name
    if aliases:
        out["aliases"] = aliases
    if logo:
        out["logo"] = logo
    if tag:
        out["tag"] = tag
    return out if len(out) > 1 or base is None else None


def load(asset_dir: Path | str = ASSETS_DIR) -> dict[str, dict]:
    """{chiave: voce} dal file (ricaricato se cambia). File assente o rotto: nessuna correzione."""
    path = overrides_path(asset_dir)
    try:
        st = path.stat()
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _cache.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("teams") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    teams = {}
    for key, entry in raw.items():
        entry = clean_entry(entry)
        if entry:
            teams[str(key)] = entry
    _cache[str(path)] = (mtime, teams)
    return teams


def _names(entry: dict) -> list[str]:
    return [n for n in (entry.get("base"), entry.get("name"), *entry.get("aliases", [])) if n]


_manifest_cache: dict[str, tuple[tuple, dict]] = {}


def _catalog_names(asset_dir: Path | str) -> dict[str, str]:
    """{nome o alias FCLogo normalizzato: nome squadra normalizzato}; i nomi ambigui sono esclusi."""
    path = Path(asset_dir) / "team_logos" / "manifest.json"
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _manifest_cache.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        teams = json.loads(path.read_text(encoding="utf-8")).get("teams") or []
    except (OSError, ValueError, AttributeError):
        return {}
    names, ambiguous = {}, set()
    for team in teams:
        if not isinstance(team, dict) or not team.get("name"):
            continue
        owner = normalize_team_name(team["name"])
        for n in [team["name"], *(team.get("aliases") or [])]:
            k = normalize_team_name(n)
            if k in names and names[k] != owner:
                ambiguous.add(k)
            names.setdefault(k, owner)
    for k in ambiguous:
        names.pop(k, None)
    _manifest_cache[str(path)] = (stamp, names)
    return names


def find(name: str, asset_dir: Path | str = ASSETS_DIR) -> dict | None:
    """Voce corretta per un nome: nomi scritti nelle correzioni, oppure qualunque nome
    con cui il catalogo FCLogo conosce la squadra corretta (es. "Internazionale")."""
    key = normalize_team_name(name)
    if not key:
        return None
    entries = load(asset_dir)
    for entry in entries.values():
        if key in {normalize_team_name(n) for n in _names(entry)}:
            return entry
    owner = _catalog_names(asset_dir).get(key)
    if owner:
        for entry in entries.values():
            if entry.get("base") and normalize_team_name(entry["base"]) == owner:
                return entry
    return None


def logo_path(name: str, asset_dir: Path | str = ASSETS_DIR) -> Path | None:
    entry = find(name, asset_dir)
    if not entry or not entry.get("logo"):
        return None
    path = Path(asset_dir) / DIRNAME / entry["logo"]
    return path if path.is_file() else None


def base_name(name: str, asset_dir: Path | str = ASSETS_DIR) -> str | None:
    """Nome della squadra FCLogo a cui è collegato un nome ESPN aggiunto a mano."""
    entry = find(name, asset_dir)
    return entry.get("base") if entry else None


# ---------- Impostazioni › Nomi: nome italiano e hashtag per nome ESPN ----------
# team_overrides/names.json = {"version": 1, "teams": {"<nome ESPN>": {"name": "...", "tag": "..."}}}
# Ha la precedenza su data/teams.json; ogni campo si può togliere da solo.
NAMES_FILE = "names.json"
_names_cache: dict[str, tuple[tuple, dict]] = {}


def names_path(asset_dir: Path | str = ASSETS_DIR) -> Path:
    return Path(asset_dir) / DIRNAME / NAMES_FILE


def load_names(asset_dir: Path | str = ASSETS_DIR) -> dict[str, dict]:
    """{nome ESPN: {"name"?, "tag"?}} dal file (ricaricato se cambia). Assente o rotto: vuoto."""
    path = names_path(asset_dir)
    try:
        st = path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _names_cache.get(str(path))
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8")).get("teams") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    out = {}
    for espn, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        clean = {k: " ".join(str(entry.get(k) or "").split()) for k in ("name", "tag")}
        clean = {k: v for k, v in clean.items() if v}
        if str(espn).strip() and clean:
            out[str(espn).strip()] = clean
    _names_cache[str(path)] = (stamp, out)
    return out


def name_entry(espn_name: str, asset_dir: Path | str = ASSETS_DIR) -> dict | None:
    """Nome italiano e hashtag scelti nella mini app per un nome ESPN (maiuscole indifferenti)."""
    names = load_names(asset_dir)
    if not names or not espn_name:
        return None
    hit = names.get(espn_name)
    if hit is None:
        low = espn_name.casefold()
        hit = next((v for k, v in names.items() if k.casefold() == low), None)
    return hit


def display_name(name: str, asset_dir: Path | str = ASSETS_DIR) -> str | None:
    entry = find(name, asset_dir)
    return entry.get("name") if entry else None


def hashtag(name: str, asset_dir: Path | str = ASSETS_DIR) -> str | None:
    """Hashtag scelto nella mini app per la squadra (senza #)."""
    entry = find(name, asset_dir)
    return entry.get("tag") if entry else None


def apply(teams: list[dict], asset_dir: Path | str = ASSETS_DIR) -> list[dict]:
    """Catalogo FCLogo (righe del manifest) con le correzioni: alias in più, nome mostrato,
    logo a mano (campo "custom_logo", percorso assoluto) e squadre nuove in coda.
    Le righe originali non vengono modificate."""
    overrides = load(asset_dir)
    if not overrides:
        return list(teams)
    out = [dict(t) for t in teams]
    by_name = {}
    for i, team in enumerate(out):
        for n in [team.get("name"), *(team.get("aliases") or [])]:
            by_name.setdefault(normalize_team_name(n or ""), i)
    folder = Path(asset_dir) / DIRNAME
    for key, entry in overrides.items():
        logo = folder / entry["logo"] if entry.get("logo") else None
        logo = str(logo) if logo and logo.is_file() else None
        if entry.get("base"):
            i = by_name.get(normalize_team_name(entry["base"]))
            if i is None:
                continue          # squadra uscita dal catalogo: correzione ignorata
            team = out[i]
            team["aliases_fclogo"] = list(team.get("aliases") or [])
            team["aliases"] = unique_aliases(list(team.get("aliases") or []) + entry.get("aliases", []))
        else:
            team = {"name": entry["name"], "aliases": list(entry.get("aliases", [])), "manual": True}
            out.append(team)
        team["override_key"] = key
        team["override"] = entry
        if entry.get("name"):
            team["display_name"] = entry["name"]
        if logo:
            team["custom_logo"] = logo
    return out


def drop_superseded_logos(fresh: list[dict], asset_dir: Path | str = ASSETS_DIR) -> list[str]:
    """Sync FCLogo: per le squadre che hanno appena ricevuto un logo MONO nuovo toglie
    il logo caricato a mano (nome e nomi ESPN restano). Una squadra creata a mano
    (base null) si collega alla squadra FCLogo appena comparsa con lo stesso nome.
    Ritorna i nomi delle squadre ripulite."""
    path = overrides_path(asset_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("teams") or {}
    except (OSError, ValueError, AttributeError):
        return []
    owners: dict[str, str | None] = {}      # nome normalizzato -> squadra FCLogo (None se ambiguo)
    for team in fresh:
        name = str(team.get("name") or "").strip()
        if not name:
            continue
        for n in [name, *(team.get("aliases") or [])]:
            k = normalize_team_name(str(n))
            if k:
                owners[k] = name if owners.get(k, name) == name else None
    cleared, dropped_files = [], []
    for key in list(raw):
        entry = clean_entry(raw[key])
        if not entry or not entry.get("logo"):
            continue
        if entry.get("base"):
            owner = owners.get(normalize_team_name(entry["base"]))
        else:
            hits = {owners.get(normalize_team_name(n)) for n in _names(entry)} - {None}
            owner = hits.pop() if len(hits) == 1 else None
            if owner:
                entry["base"] = owner
        if not owner:
            continue
        dropped_files.append(entry.pop("logo"))
        cleared.append(entry.get("name") or owner)
        entry = clean_entry(entry)
        if entry:
            raw[key] = entry
        else:
            del raw[key]
    if not cleared:
        return []
    data["teams"] = dict(sorted(raw.items()))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    still_used = {str(e.get("logo")) for e in raw.values() if isinstance(e, dict) and e.get("logo")}
    for rel in dropped_files:
        if rel not in still_used:
            (path.parent / rel).unlink(missing_ok=True)
    return sorted(cleared)
