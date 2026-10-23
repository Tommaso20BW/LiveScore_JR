"""Sincronizza i loghi FCLogo della stagione corrente.

Scarica sempre i pack Serie A, Serie B, Champions League, Europa League e
Conference League, indipendentemente da dove gioca la Juventus. Al cambio di
stagione il catalogo precedente viene sostituito da quello nuovo.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from livescore.core.team_matching import normalize_team_name as _normalize, unique_aliases
from livescore.paths import ASSETS_DIR


BASE_URL = "https://fclogo.top"
ASSET_BASE_URL = "https://assets.fclogo.top/png"
DEFAULT_LOGO_DIR = ASSETS_DIR / "team_logos"
MANIFEST_FILENAME = "manifest.json"
# Vecchia sottocartella unica: letta una volta per migrare manifest e alias, poi rimossa.
LEGACY_DIRNAME = "fclogo_cache"
# Una cartella per competizione, in ordine di priorita': la prima e' quella del
# campo "file" del manifest; una squadra in piu' competizioni ha una copia in ognuna.
COMPETITION_FOLDERS = (
    ("serie-a", "serie-a"),
    ("serie-b", "serie-b"),
    ("uefa-champions-league", "ucl"),
    ("uefa-europa-league", "uel"),
    ("uefa-conference-league", "uecl"),
)
USER_AGENT = "LiveScore_JR/1.0 (+https://github.com/Tommaso20BW/LiveScore_JR)"
MAX_PACK_PAGES = 8
MAX_PARALLEL_DOWNLOADS = 3


class FCLogoSyncError(RuntimeError):
    """Errore non fatale nella sincronizzazione del catalogo FCLogo."""


@dataclass(frozen=True)
class ClubRecord:
    slug: str
    name: str
    preview_url: str = ""
    detail_path: str = ""


@dataclass
class SyncReport:
    season: str
    selected_packs: tuple[str, ...] = ()
    teams: int = 0
    downloaded: int = 0
    reused: int = 0
    removed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        packs = ", ".join(self.selected_packs) if self.selected_packs else "nessuno"
        return (
            f"FCLogo {self.season}: pack [{packs}], {self.teams} squadre, "
            f"{self.downloaded} aggiornati, {self.reused} riutilizzati, "
            f"{self.removed} rimossi, "
            f"{self.failed} errori"
        )


class _PackLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slugs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        match = re.fullmatch(r"/pack/([^/?#]+)", href)
        if match:
            self.slugs.append(match.group(1))


class _ClubParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._active_slug = ""
        self.clubs: dict[str, ClubRecord] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href") or ""
            match = re.search(r"/club/([^/?#]+)", href)
            self._active_slug = match.group(1) if match else ""
            if self._active_slug and self._active_slug not in self.clubs:
                self.clubs[self._active_slug] = ClubRecord(
                    slug=self._active_slug,
                    name=_display_name_from_slug(self._active_slug),
                    detail_path=href,
                )
            return
        if tag != "img" or not self._active_slug:
            return
        current = self.clubs[self._active_slug]
        preview_url = attributes.get("src") or attributes.get("data-src") or ""
        alt_name = _clean_alt_name(attributes.get("alt") or "")
        self.clubs[self._active_slug] = ClubRecord(
            slug=current.slug,
            name=alt_name or current.name,
            preview_url=preview_url or current.preview_url,
            detail_path=current.detail_path,
        )

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._active_slug = ""


def season_start_year(today: date | None = None) -> int:
    current = today or date.today()
    return current.year if current.month >= 7 else current.year - 1


def season_label(today: date | None = None) -> str:
    start = season_start_year(today)
    return f"{start}-{str(start + 1)[-2:]}"


def _display_name_from_slug(slug: str) -> str:
    clean = re.sub(r"-mono$", "", slug, flags=re.IGNORECASE)
    clean = re.sub(r"-v\d{4}(?:-[a-z0-9]+)*$", "", clean, flags=re.IGNORECASE)
    return " ".join(part.upper() if len(part) <= 3 else part.title() for part in clean.split("-"))


def _clean_alt_name(value: str) -> str:
    clean = re.sub(
        r"\s+(?:football\s+club\s+)?logo(?:\s+monochrome)?\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()
    return clean


def _get(session: requests.Session, url: str, timeout: int = 15) -> requests.Response:
    response = session.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,image/png,*/*"},
        timeout=timeout,
    )
    response.raise_for_status()
    return response


def _new_session() -> requests.Session:
    session = requests.Session()
    # FCLogo risponde 503 se lo si interroga troppo in fretta: piu' tentativi con
    # attese crescenti (1s, 2s, 4s, 8s) e rispetto di Retry-After, cosi' un picco
    # non fa fallire il giro e non invalida la cache del manifest.
    retry = Retry(
        total=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
    return session


def discover_pack_slugs(
    session: requests.Session,
    start_year: int,
    *,
    max_pages: int = MAX_PACK_PAGES,
) -> list[str]:
    """Scopre gli slug dal catalogo senza assumere il formato dell'anno."""
    found: list[str] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/packs?season={start_year}&page={page}"
        try:
            parser = _PackLinkParser()
            parser.feed(_get(session, url).text)
        except requests.RequestException as exc:
            if page == 1:
                raise FCLogoSyncError(f"catalogo non raggiungibile: {exc}") from exc
            break
        new_slugs = [slug for slug in parser.slugs if slug not in seen]
        if not new_slugs:
            break
        found.extend(new_slugs)
        seen.update(new_slugs)
    return found


def _is_domestic_pack(slug: str) -> bool:
    return bool(re.fullmatch(r"(?:\d{2}|\d{4})-\d{2}-serie-[ab]", slug))


def _is_uefa_pack(slug: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:\d{2}|\d{4})-\d{2}-uefa-(?:champions-league|europa-league|conference-league)",
            slug,
        )
    )


def candidate_pack_slugs(pack_slugs: list[str]) -> list[str]:
    return [slug for slug in pack_slugs if _is_domestic_pack(slug) or _is_uefa_pack(slug)]


def parse_pack_clubs(page_html: str) -> list[ClubRecord]:
    parser = _ClubParser()
    parser.feed(page_html)
    return sorted(parser.clubs.values(), key=lambda club: club.slug.casefold())


def pack_fingerprint(clubs: list[ClubRecord]) -> str:
    payload = "\n".join(
        f"{club.slug}|{club.preview_url}|{club.detail_path}" for club in clubs
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_pack_records(
    session: requests.Session,
    pack_slugs: list[str],
) -> tuple[dict[str, list[ClubRecord]], list[str]]:
    """Tutti i pack Serie A/B e UEFA (UCL, UEL, UECL) della stagione."""
    selected: dict[str, list[ClubRecord]] = {}
    errors: list[str] = []
    for slug in candidate_pack_slugs(pack_slugs):
        try:
            clubs = parse_pack_clubs(_get(session, f"{BASE_URL}/pack/{slug}").text)
        except requests.RequestException as exc:
            errors.append(f"{slug}: {exc}")
            continue
        if not clubs:
            errors.append(f"{slug}: nessuna squadra trovata")
            continue
        selected[slug] = clubs
    return selected, errors


def competition_folder(pack_slug: str) -> str:
    for suffix, folder in COMPETITION_FOLDERS:
        if pack_slug.endswith(f"-{suffix}"):
            return folder
    return "altro"


def _club_folders(pack_slugs: set[str]) -> list[str]:
    order = [folder for _, folder in COMPETITION_FOLDERS] + ["altro"]
    return sorted({competition_folder(slug) for slug in pack_slugs}, key=order.index)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _valid_png(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            return rgba.width > 0 and rgba.height > 0 and rgba.getchannel("A").getbbox() is not None
    except (OSError, ValueError):
        return False


def _validate_png_bytes(content: bytes) -> None:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            rgba = image.convert("RGBA")
            if rgba.width <= 0 or rgba.height <= 0 or rgba.getchannel("A").getbbox() is None:
                raise ValueError("PNG vuoto")
    except (OSError, ValueError) as exc:
        raise FCLogoSyncError(f"asset PNG non valido: {exc}") from exc


def _safe_filename(slug: str, variant: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", re.sub(r"-mono$", "", slug, flags=re.I))
    return f"{base}-{variant}.png"


class _MetaImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = (attributes.get("property") or attributes.get("name") or "").casefold()
        content = attributes.get("content") or ""
        if key in ("og:image", "twitter:image") and content.startswith("https://"):
            self.urls.append(content)


def _asset_url_from_detail(page_html: str, *, variant: str) -> str:
    parser = _MetaImageParser()
    parser.feed(page_html)
    expected_suffix = f"-{variant}.png"
    for url in parser.urls:
        if url.startswith(f"{ASSET_BASE_URL}/") and url.casefold().endswith(expected_suffix):
            return url
    for url in parser.urls:
        if url.startswith(f"{ASSET_BASE_URL}/") and url.casefold().endswith(".png"):
            return url
    raise FCLogoSyncError("pagina senza URL PNG ufficiale")


class _VariantTabParser(HTMLParser):
    """Legge le linguette "Color"/"Mono" sotto il logo nella pagina del club.

    Alcuni club non hanno una pagina "-mono" separata: la versione mono e' solo
    una linguetta, gia' presente nell'HTML del server (immagine su Sanity con
    alt "<club> - Mono"). Senza parametri l'URL Sanity restituisce il PNG originale.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attributes = dict(attrs)
        match = re.search(r"\s-\s(mono|color)\s*$", attributes.get("alt") or "", re.IGNORECASE)
        source = (attributes.get("src") or "").split("?", 1)[0]
        if match and source.startswith("https://cdn.sanity.io/") and source.casefold().endswith(".png"):
            self.urls.setdefault(match.group(1).casefold(), source)


def _mono_tab_url(page_html: str) -> str:
    parser = _VariantTabParser()
    parser.feed(page_html)
    return parser.urls.get("mono", "")


def _detail_url(club: ClubRecord, variant: str) -> str:
    path = club.detail_path or f"/club/{club.slug}"
    path = re.sub(r"-mono$", "", path, flags=re.IGNORECASE)
    if variant == "mono":
        path += "-mono"
    return f"{BASE_URL}{path if path.startswith('/') else '/' + path}"


def _download_logo(
    session: requests.Session,
    club: ClubRecord,
    output_dir: Path,
    folder: str,
) -> tuple[str, str, str]:
    """Salva sempre il PNG mono. Ordine: pagina "-mono" ufficiale, linguetta Mono
    nella pagina del club; se FCLogo pubblica un'unica versione, quella e' gia'
    il mono e si salva cosi' com'e'. Restituisce (file, variante, url)."""
    base_slug = re.sub(r"-mono$", "", club.slug, flags=re.IGNORECASE)
    errors: list[str] = []
    for variant in ("mono", "color"):
        try:
            detail_response = _get(session, _detail_url(club, variant))
            tab_url = _mono_tab_url(detail_response.text) if variant == "color" else ""
            url = tab_url or _asset_url_from_detail(detail_response.text, variant=variant)
            response = _get(session, url)
            _validate_png_bytes(response.content)
        except (requests.RequestException, FCLogoSyncError) as exc:
            errors.append(f"{variant}: {exc}")
            continue
        filename = f"{folder}/{_safe_filename(base_slug, 'mono')}"
        destination = output_dir / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".png.tmp")
        temporary.write_bytes(response.content)
        temporary.replace(destination)
        return filename, "mono", url
    raise FCLogoSyncError("; ".join(errors))


def _club_aliases(club: ClubRecord) -> list[str]:
    derived = _display_name_from_slug(club.slug)
    return sorted({alias for alias in (club.name, derived) if alias})


def _club_key(item: dict) -> tuple[str, str]:
    """Identita' FCLogo senza versione, senza matching approssimativo."""
    path = str(item.get("detail_path", ""))
    federation = path.split("/club/", 1)[0].casefold() if "/club/" in path else ""
    return federation, _normalize(_display_name_from_slug(str(item.get("slug", ""))))


def preserve_manifest_aliases(teams: dict, previous: dict) -> None:
    """Conserva gli alias editati a mano anche quando cambia v2025 -> v2026."""
    by_club: dict[tuple[str, str], list[dict]] = {}
    for old in previous.values():
        by_club.setdefault(_club_key(old), []).append(old)
    for slug, item in teams.items():
        old = previous.get(slug)
        if old is None:
            candidates = by_club.get(_club_key(item), [])
            old = candidates[0] if len(candidates) == 1 else {}
        # Il manifest e' l'unica fonte degli alias manuali, non ESPN.
        item["aliases"] = unique_aliases(
            item.get("aliases", []) + old.get("aliases", [])
        )
        for field in ("espn_id", "espn_aliases", "espn_source_url", "espn_match_status"):
            item.pop(field, None)


def sync_current_season(
    *,
    output_dir: Path | str = DEFAULT_LOGO_DIR,
    session: requests.Session | None = None,
    today: date | None = None,
) -> SyncReport:
    """Controlla i pack correnti e aggiorna solo asset mancanti o cambiati."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / MANIFEST_FILENAME
    previous = _read_manifest(manifest_path)
    legacy_dir = output_dir / LEGACY_DIRNAME
    if not previous and (legacy_dir / MANIFEST_FILENAME).is_file():
        # Migrazione da team_logos/fclogo_cache: i file vecchi restano riusabili.
        previous = _read_manifest(legacy_dir / MANIFEST_FILENAME)
        for item in previous.get("teams", []):
            if isinstance(item, dict) and item.get("file"):
                item["file"] = f"{LEGACY_DIRNAME}/{item['file']}"
    previous_teams = {
        str(item.get("slug", "")): item
        for item in previous.get("teams", [])
        if isinstance(item, dict) and item.get("slug")
    }

    http = session or _new_session()
    label = season_label(today)
    slugs = discover_pack_slugs(http, season_start_year(today))
    selected, errors = select_pack_records(http, slugs)
    report = SyncReport(
        season=label,
        selected_packs=tuple(sorted(selected)),
        errors=list(errors),
        failed=len(errors),
    )
    if not selected:
        raise FCLogoSyncError(
            f"nessun pack Serie A/Serie B o UEFA valido trovato per {label}"
        )

    club_packs: dict[str, set[str]] = {}
    clubs_by_slug: dict[str, ClubRecord] = {}
    for pack_slug, clubs in selected.items():
        for club in clubs:
            clubs_by_slug[club.slug] = club
            club_packs.setdefault(club.slug, set()).add(pack_slug)

    # Non trasciniamo squadre di stagioni passate. Se un singolo pack della
    # stagione corrente non risponde, conserviamo invece le sue ultime copie
    # valide finche il controllo successivo non riesce.
    failed_pack_slugs = {
        error.split(":", 1)[0]
        for error in errors
        if ":" in error
    }
    updated_teams = {
        slug: item
        for slug, item in previous_teams.items()
        if previous.get("season") == label
        and any(pack in failed_pack_slugs for pack in item.get("packs", []))
    }
    pending_downloads: list[tuple[str, ClubRecord, dict[str, Any], Path]] = []
    for club_slug, club in sorted(clubs_by_slug.items()):
        old = previous_teams.get(club_slug, {})
        old_path = output_dir / str(old.get("file", ""))
        unchanged = (
            previous.get("season") == label
            and old.get("preview_url", "") == club.preview_url
            and old.get("variant") == "mono"
            and _valid_png(old_path)
        )
        if unchanged:
            filename = f"{_club_folders(club_packs[club_slug])[0]}/{old_path.name}"
            variant = str(old.get("variant", "mono"))
            source_url = str(old.get("source_url", ""))
            report.reused += 1
            updated_teams[club_slug] = {
                "name": club.name,
                "slug": club_slug,
                "file": filename,
                "aliases": _club_aliases(club),
                "variant": variant,
                "source_url": source_url,
                "preview_url": club.preview_url,
                "detail_path": club.detail_path,
                "packs": sorted(club_packs[club_slug]),
            }
        else:
            pending_downloads.append((club_slug, club, old, old_path))

    def fetch_logo(
        item: tuple[str, ClubRecord, dict[str, Any], Path],
    ) -> tuple[str, ClubRecord, str, str, str, bool, str]:
        club_slug, club, old, old_path = item
        download_http = http if session is not None else _new_session()
        try:
            filename, variant, source_url = _download_logo(
                download_http, club, output_dir, _club_folders(club_packs[club_slug])[0]
            )
            return club_slug, club, filename, variant, source_url, True, ""
        except FCLogoSyncError as exc:
            if previous.get("season") == label and _valid_png(old_path):
                return (
                    club_slug,
                    club,
                    f"{_club_folders(club_packs[club_slug])[0]}/{old_path.name}",
                    str(old.get("variant", "cached")),
                    str(old.get("source_url", "")),
                    False,
                    "",
                )
            return club_slug, club, "", "", "", False, str(exc)

    if session is not None or len(pending_downloads) <= 1:
        fetched = map(fetch_logo, pending_downloads)
    else:
        executor = ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_DOWNLOADS, len(pending_downloads)))
        fetched = executor.map(fetch_logo, pending_downloads)

    try:
        for club_slug, club, filename, variant, source_url, downloaded, error in fetched:
            if error:
                report.failed += 1
                report.errors.append(f"{club.name}: {error}")
                continue
            if downloaded:
                report.downloaded += 1
            else:
                report.reused += 1
            updated_teams[club_slug] = {
                "name": club.name,
                "slug": club_slug,
                "file": filename,
                "aliases": _club_aliases(club),
                "variant": variant,
                "source_url": source_url,
                "preview_url": club.preview_url,
                "detail_path": club.detail_path,
                "packs": sorted(club_packs[club_slug]),
            }
    finally:
        if session is None and len(pending_downloads) > 1:
            executor.shutdown(wait=True)

    preserve_manifest_aliases(updated_teams, previous_teams)

    # Copie per competizione: il file principale nasce (o si sposta) nella prima
    # cartella, poi si copia nelle altre competizioni della squadra.
    for club_slug, item in updated_teams.items():
        name = Path(str(item.get("file", ""))).name
        if not name:
            continue
        folders = _club_folders(set(item.get("packs", []))) if club_slug in clubs_by_slug else []
        old = previous_teams.get(club_slug, {})
        sources = [output_dir / str(item["file"]), output_dir / str(old.get("file", ""))]
        source = next((path for path in sources if path.is_file() and _valid_png(path)), None)
        if source is None:
            continue
        files = [f"{folder}/{name}" for folder in folders] or [str(item["file"])]
        for relative in files:
            target = output_dir / relative
            if target.resolve() == source.resolve():
                continue
            if not target.is_file() or target.read_bytes() != source.read_bytes():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        item["file"] = files[0]
        item["files"] = files

    manifest = {
        "source": f"{BASE_URL}/",
        "season": label,
        "packs": {
            slug: {
                "url": f"{BASE_URL}/pack/{slug}",
                "fingerprint": pack_fingerprint(clubs),
                "clubs": [club.slug for club in clubs],
            }
            for slug, clubs in sorted(selected.items())
        },
        "teams": sorted(updated_teams.values(), key=lambda item: str(item.get("slug", ""))),
    }
    if report.failed == 0:
        temporary_manifest = manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_manifest.replace(manifest_path)

        # La cartella è dedicata al catalogo FCLogo: dopo aver pubblicato il
        # nuovo manifest rimuoviamo i PNG non più referenziati. Questo elimina
        # squadre uscite e vecchie versioni di stemmi al cambio stagione.
        referenced_files = {
            relative
            for item in manifest["teams"]
            for relative in (item.get("files") or [item.get("file", "")])
            if relative
        }
        for logo_path in sorted(output_dir.rglob("*.png")):
            if logo_path.relative_to(output_dir).as_posix() not in referenced_files:
                logo_path.unlink()
                report.removed += 1
        if legacy_dir.is_dir():
            shutil.rmtree(legacy_dir)
        for folder in sorted(output_dir.iterdir()):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()

    report.teams = len(clubs_by_slug)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincronizza i loghi stagionali FCLogo")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_LOGO_DIR)
    args = parser.parse_args()
    try:
        report = sync_current_season(output_dir=args.output_dir)
    except FCLogoSyncError as exc:
        print(f"FCLogo: sincronizzazione non riuscita ({exc})")
        return 1
    print(report.summary())
    for error in report.errors:
        print(f"FCLogo warning: {error}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
