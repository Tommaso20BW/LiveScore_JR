#!/usr/bin/env python3
"""
TEST REALE 5 MINUTI - Dynamic Kit Juventus
Evento ESPN reale: 401874750

Il test NON avvia il LiveScore principale e NON usa il Gist di produzione.
Invia solo a TELEGRAM_TO_BOT.

Verifica realmente:
- summary ESPN reale ogni ~6 secondi
- uniform.type Juventus reale
- HOME / AWAY / THIRD / AUTO tramite callback Telegram
- renderer ufficiali del repository
- Canva PRO reale con refresh token di produzione
- pagina Canva 1 = HALF TIME
- pagina Canva 2 = FULL TIME
- snapshot Canva separati e persistenti su branch runtime-snapshots
- eliminazione locale degli snapshot per simulare un restart runner
- recupero remoto con verifica SHA256
- editMessageMedia sullo stesso message_id
- stats reali della partita
- rimozione pulsanti e cleanup remoto a fine test
"""

from __future__ import annotations

import base64
import copy
import hashlib
import html
import io
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

from PIL import Image

import juve_bot_espn as bot
import goal_graphics
import portrait_graphics
import stats_graphics
from canva_page_one import extract_layers


EVENT_ID = "401874750"
LEAGUE_SLUG = "ita.1"
LEAGUE_NAME = "SERIE A"
DURATION_SECONDS = int(os.getenv("KIT_REAL_TEST_DURATION_SECONDS", "300"))
POLL_SECONDS = float(os.getenv("KIT_REAL_TEST_POLL_SECONDS", "6"))
BOT_JR = str(os.getenv("TELEGRAM_TO_BOT") or "").strip()

SNAPSHOT_BRANCH = "runtime-snapshots"
SNAPSHOT_TOKEN = str(
    os.getenv("SNAPSHOT_GH_TOKEN")
    or os.getenv("GH_PAT")
    or ""
).strip()
REPOSITORY = str(os.getenv("GITHUB_REPOSITORY") or "").strip()
RUN_KEY = re.sub(
    r"[^A-Za-z0-9._-]+",
    "_",
    os.getenv(
        "SNAPSHOT_TEST_KEY",
        f"test_{EVENT_ID}_{os.getenv('GITHUB_RUN_ID', 'local')}",
    ),
).strip("._")
REMOTE_PREFIX = f"runtime_snapshots/{RUN_KEY}/"

LOCAL_CACHE = Path("canva_real_test_cache_401874750")
RECOVERY_CACHE = Path("canva_real_test_recovery_401874750")
VALID_KITS = ("home", "away", "third")
REQUIRED_SNAPSHOT_FILES = (
    "source.pdf",
    "background.png",
    "player.png",
    "manifest.json",
)

# goal_graphics.py usa gia' io.BytesIO nel fallback ESPN. Nel main nuovo il
# runtime applica questo shim; nel test lo facciamo localmente senza modificare
# goal_graphics.py.
if not hasattr(goal_graphics, "io"):
    goal_graphics.io = io


def log(message: str) -> None:
    print(
        f"[REAL-KIT-TEST {time.strftime('%H:%M:%S')}] {message}",
        flush=True,
    )


def normalise_kit(value) -> str | None:
    value = str(value or "").strip().lower()
    return value if value in VALID_KITS else None


def display_kit(value: str | None) -> str:
    return {
        "home": "Home",
        "away": "Away",
        "third": "Third",
    }.get(value, "Non disponibile")


def pixel_hash(png: bytes) -> str:
    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        raw = f"{rgba.width}x{rgba.height}:".encode() + rgba.tobytes()
    return hashlib.sha256(raw).hexdigest()


def fetch_summary() -> dict:
    data = bot.fetch_evento(EVENT_ID, LEAGUE_SLUG)
    if not isinstance(data, dict):
        raise RuntimeError(
            f"ESPN summary non disponibile per event={EVENT_ID}"
        )
    return data


def match_info(data: dict):
    competitions = ((data.get("header") or {}).get("competitions") or [])
    if not competitions:
        raise RuntimeError("ESPN: header.competitions assente")
    competition = competitions[0]
    competitors = competition.get("competitors") or []
    if len(competitors) != 2:
        raise RuntimeError("ESPN: competitors non validi")
    return (*bot.parse_score(competitors), competition)


def extract_juve_uniform(data: dict) -> str | None:
    teams = ((data.get("boxscore") or {}).get("teams") or [])
    for item in teams:
        team = (item or {}).get("team") or {}
        if str(team.get("id") or "") == str(bot.JUVE_ID):
            return normalise_kit((team.get("uniform") or {}).get("type"))

    # Fallback nel caso ESPN ometta team.id da boxscore.teams.
    home_id, away_id, *_ = match_info(data)
    juve_side = "home" if str(home_id) == str(bot.JUVE_ID) else "away"
    for item in teams:
        if (item or {}).get("homeAway") == juve_side:
            return normalise_kit(
                ((((item or {}).get("team") or {}).get("uniform")) or {}).get("type")
            )
    return None


def get_fallback_kit(data: dict) -> str:
    home_id, away_id, home_name, away_name, *_ = match_info(data)
    kit = bot.determina_kit(
        home_id,
        away_id,
        LEAGUE_SLUG,
        LEAGUE_NAME,
    )
    return normalise_kit(kit) or "away"


def _clock_minutes(value) -> float:
    raw = str(value or "").replace("’", "'")
    # "45'+2'" / "45:00" / "54'"
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if not nums:
        return 999.0
    if "+" in raw and len(nums) >= 2:
        return float(nums[0]) + nums[1] / 100.0
    return float(nums[0])


def scoring_items(data: dict) -> list[dict]:
    competition = match_info(data)[-1]
    sources = []
    for value in (
        data.get("scoringPlays"),
        competition.get("details"),
        data.get("plays"),
    ):
        if isinstance(value, list):
            sources.extend(value)

    result = []
    seen = set()
    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            continue
        type_obj = item.get("type") or {}
        type_text = str(
            type_obj.get("text")
            or type_obj.get("description")
            or item.get("typeText")
            or ""
        )
        text = str(
            item.get("text")
            or item.get("headline")
            or type_text
            or ""
        )
        low = f"{type_text} {text}".lower()

        is_goal = bool(item.get("scoringPlay")) or "goal" in low
        if not is_goal:
            continue

        team = item.get("team") or {}
        team_id = str(
            team.get("id")
            or item.get("teamId")
            or ""
        )

        period_obj = item.get("period") or {}
        period = period_obj.get("number") if isinstance(period_obj, dict) else period_obj

        clock = item.get("clock") or {}
        minute = (
            clock.get("displayValue")
            if isinstance(clock, dict)
            else None
        ) or item.get("clockDisplayValue") or item.get("minute") or "?"

        player = ""
        for participant in item.get("participants") or []:
            athlete = (participant or {}).get("athlete") or {}
            player = (
                athlete.get("displayName")
                or athlete.get("shortName")
                or ""
            )
            if player:
                break

        if not player:
            athlete = item.get("athlete") or {}
            player = (
                athlete.get("displayName")
                or athlete.get("shortName")
                or ""
            )

        if not player and text:
            match = re.search(
                r"Goal!\s*[^.]+?\.\s*([^(.\n]+?)\s*\(([^)]+)\)",
                text,
                re.I,
            )
            if match:
                player = match.group(1).strip()

        key = (
            str(item.get("id") or ""),
            team_id,
            player,
            str(minute),
            type_text,
        )
        if key in seen:
            continue
        seen.add(key)

        result.append({
            "index": index,
            "team_id": team_id,
            "player": player,
            "minute": minute,
            "period": int(period) if str(period).isdigit() else None,
            "goal_type": (
                "own goal"
                if "own goal" in low
                else "penalty goal"
                if "penalty" in low
                else "goal"
            ),
            "sort": (
                int(period) if str(period).isdigit() else 9,
                _clock_minutes(minute),
                index,
            ),
        })

    result.sort(key=lambda x: x["sort"])
    return result


def production_goal_events(data: dict) -> list[dict]:
    """Usa ESATTAMENTE parse_events() e goal_scoring_team_id() del bot reale."""
    home_id, away_id, home_name, away_name, *_ = match_info(data)
    events = bot.parse_events(
        data,
        home_name,
        away_name,
        str(home_id),
        str(away_id),
    )

    goals = []
    for event in events:
        if event.get("type") not in (
            "goal",
            "penalty goal",
            "own goal",
        ):
            continue
        item = dict(event)
        item["scoring_team_id"] = bot.goal_scoring_team_id(
            item,
            str(home_id),
            str(away_id),
        )
        goals.append(item)

    def sort_key(event):
        period = int(event.get("period") or 0)
        minute = int(event.get("minute") or 0)
        # Se ESPN non ha valorizzato il periodo, il minuto mantiene comunque
        # l'ordine regolamentare. Il seq del parser produzione fa da tiebreaker.
        inferred_period = period or (1 if minute <= 45 else 2)
        return (
            inferred_period,
            minute,
            int(event.get("seq") or 0),
        )

    return sorted(goals, key=sort_key)


def _display_base_minute(value) -> int:
    raw = str(value or "").replace("’", "'").replace("'", "")
    first = raw.split("+", 1)[0].split(":", 1)[0].strip()
    try:
        return int(float(first))
    except Exception:
        return 999


def halftime_score(data: dict) -> tuple[int, int]:
    home_id, away_id, *_ = match_info(data)
    home = away = 0

    for event in production_goal_events(data):
        period = int(event.get("period") or 0)
        minute_disp = event.get("minute_disp") or event.get("minute") or ""
        first_half = (
            period == 1
            or (
                period == 0
                and _display_base_minute(minute_disp) <= 45
            )
        )
        if not first_half:
            continue

        scoring_team = str(event.get("scoring_team_id") or "")
        if scoring_team == str(home_id):
            home += 1
        elif scoring_team == str(away_id):
            away += 1

    return home, away


def real_juve_goal(data: dict) -> dict:
    """Primo vero gol Juve secondo lo stesso parser/dedup del LiveScore."""
    home_id, away_id, *_ = match_info(data)
    score_h = score_a = 0

    for event in production_goal_events(data):
        scoring_team = str(event.get("scoring_team_id") or "")

        if scoring_team == str(home_id):
            score_h += 1
        elif scoring_team == str(away_id):
            score_a += 1

        player = str(event.get("player_name") or "").strip()
        if scoring_team == str(bot.JUVE_ID) and player:
            return {
                "team_id": scoring_team,
                "player": player,
                "minute": (
                    event.get("minute_disp")
                    or event.get("minute")
                    or "?"
                ),
                "period": int(event.get("period") or 0),
                "goal_type": event.get("type") or "goal",
                "home_goals": score_h,
                "away_goals": score_a,
                "uid": str(event.get("uid") or ""),
            }

    raise RuntimeError(
        "Il parser eventi reale non ha trovato un gol Juventus utilizzabile"
    )


# =============================================================================
# CANVA REALE: pagina 1 HT, pagina 2 FT
# =============================================================================

def export_canva_page(page_number: int) -> Path:
    token = bot.get_valid_token()
    if not token:
        raise RuntimeError("Canva: access token non disponibile")

    headers = {"Authorization": f"Bearer {token}"}
    response = bot.SESSION.post(
        "https://api.canva.com/rest/v1/exports",
        headers=headers,
        json={
            "design_id": bot.CANVA_DESIGN_ID,
            "format": {
                "type": "pdf",
                "pages": [page_number],
                "export_quality": "pro",
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    job = response.json()
    job = job.get("job", job)
    job_id = job["id"]
    log(f"CANVA: export PDF PRO reale pagina {page_number} richiesto")

    for _ in range(60):
        time.sleep(3)
        response = bot.SESSION.get(
            f"https://api.canva.com/rest/v1/exports/{job_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        job = response.json()
        job = job.get("job", job)
        if job.get("status") == "failed":
            raise RuntimeError(
                f"Canva: export pagina {page_number} fallito"
            )
        if job.get("status") == "success":
            response = bot.SESSION.get(
                job["urls"][0],
                timeout=60,
            )
            response.raise_for_status()
            pdf = response.content
            digest = hashlib.sha256(pdf).hexdigest()[:20]
            destination = (
                LOCAL_CACHE
                / f"page_{page_number}"
                / digest
            )
            extract_layers(pdf, destination)
            log(
                f"CANVA: pagina {page_number} congelata | "
                f"{destination}"
            )
            return destination

    raise TimeoutError(
        f"Canva: export pagina {page_number} scaduto"
    )


# =============================================================================
# SNAPSHOT REMOTO REALE SU runtime-snapshots
# =============================================================================

class SnapshotStore:
    def __init__(self):
        self.session = bot.SESSION

    @property
    def enabled(self):
        return bool(
            SNAPSHOT_TOKEN
            and REPOSITORY
            and "/" in REPOSITORY
        )

    def headers(self):
        return {
            "Authorization": f"Bearer {SNAPSHOT_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def url(self, suffix=""):
        return (
            f"https://api.github.com/repos/{REPOSITORY}/"
            f"{suffix.lstrip('/')}"
        )

    def request(
        self,
        method,
        suffix,
        *,
        expected=(200,),
        timeout=30,
        **kwargs,
    ):
        if not self.enabled:
            raise RuntimeError(
                "Snapshot remoto non configurato"
            )
        response = self.session.request(
            method,
            self.url(suffix),
            headers=self.headers(),
            timeout=timeout,
            **kwargs,
        )
        if response.status_code not in expected:
            raise RuntimeError(
                f"GitHub {method} {suffix}: "
                f"HTTP {response.status_code} · "
                f"{response.text[:800]}"
            )
        return response

    def create_blob(self, content: bytes) -> str:
        payload = self.request(
            "POST",
            "git/blobs",
            expected=(201,),
            json={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
            timeout=60,
        ).json()
        sha = str(payload.get("sha") or "")
        if not sha:
            raise RuntimeError("GitHub blob SHA assente")
        return sha

    def ensure_branch(self) -> str:
        encoded = quote(SNAPSHOT_BRANCH, safe="")
        response = self.session.get(
            self.url(f"git/ref/heads/{encoded}"),
            headers=self.headers(),
            timeout=20,
        )
        if response.status_code == 200:
            return str(
                ((response.json().get("object") or {}).get("sha"))
                or ""
            )
        if response.status_code != 404:
            raise RuntimeError(
                f"Lettura branch: HTTP {response.status_code}"
            )

        readme_blob = self.create_blob(
            (
                "# Runtime snapshots\n\n"
                "Branch tecnico LiveScore JR.\n"
            ).encode("utf-8")
        )
        tree = self.request(
            "POST",
            "git/trees",
            expected=(201,),
            json={
                "tree": [{
                    "path": "README.md",
                    "mode": "100644",
                    "type": "blob",
                    "sha": readme_blob,
                }]
            },
        ).json()
        commit = self.request(
            "POST",
            "git/commits",
            expected=(201,),
            json={
                "message": "Initialize runtime snapshot storage",
                "tree": tree["sha"],
                "parents": [],
            },
        ).json()
        create = self.session.post(
            self.url("git/refs"),
            headers=self.headers(),
            json={
                "ref": f"refs/heads/{SNAPSHOT_BRANCH}",
                "sha": commit["sha"],
            },
            timeout=20,
        )
        if create.status_code not in (201, 422):
            raise RuntimeError(
                f"Creazione branch: HTTP {create.status_code} · "
                f"{create.text[:800]}"
            )

        ref = self.request(
            "GET",
            f"git/ref/heads/{encoded}",
        ).json()
        log(f"Branch tecnico pronto: {SNAPSHOT_BRANCH}")
        return str(
            ((ref.get("object") or {}).get("sha"))
            or ""
        )

    def head_and_tree(self):
        head = self.ensure_branch()
        commit = self.request(
            "GET",
            f"git/commits/{head}",
        ).json()
        tree_sha = str(
            ((commit.get("tree") or {}).get("sha"))
            or ""
        )
        if not tree_sha:
            raise RuntimeError("Tree SHA branch snapshot assente")
        return head, tree_sha

    def commit_entries(
        self,
        entries: list[dict],
        message: str,
        retries: int = 3,
    ):
        last = None
        for attempt in range(1, retries + 1):
            try:
                parent, base_tree = self.head_and_tree()
                tree = self.request(
                    "POST",
                    "git/trees",
                    expected=(201,),
                    json={
                        "base_tree": base_tree,
                        "tree": entries,
                    },
                ).json()
                commit = self.request(
                    "POST",
                    "git/commits",
                    expected=(201,),
                    json={
                        "message": message,
                        "tree": tree["sha"],
                        "parents": [parent],
                    },
                ).json()
                update = self.session.patch(
                    self.url(
                        f"git/refs/heads/"
                        f"{quote(SNAPSHOT_BRANCH, safe='')}"
                    ),
                    headers=self.headers(),
                    json={
                        "sha": commit["sha"],
                        "force": False,
                    },
                    timeout=30,
                )
                if update.status_code == 200:
                    return
                if update.status_code in (409, 422):
                    last = RuntimeError(
                        f"ref mosso, retry {attempt}/{retries}"
                    )
                    continue
                raise RuntimeError(
                    f"PATCH ref: HTTP {update.status_code} · "
                    f"{update.text[:800]}"
                )
            except Exception as exc:
                last = exc
                if attempt == retries:
                    break
        raise RuntimeError(
            f"Commit snapshot fallito: {last}"
        )

    def archive(self, folder: Path) -> bytes:
        missing = [
            name
            for name in REQUIRED_SNAPSHOT_FILES
            if not (folder / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                "Snapshot incompleto: " + ", ".join(missing)
            )

        stream = io.BytesIO()
        with zipfile.ZipFile(
            stream,
            "w",
            zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name in REQUIRED_SNAPSHOT_FILES:
                info = zipfile.ZipInfo(
                    name,
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(
                    info,
                    (folder / name).read_bytes(),
                )
        return stream.getvalue()

    def lookup(self, path: str):
        response = self.session.get(
            self.url(
                f"contents/{quote(path, safe='/')}"
            ),
            headers=self.headers(),
            params={"ref": SNAPSHOT_BRANCH},
            timeout=30,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"Lookup snapshot: HTTP {response.status_code} · "
                f"{response.text[:800]}"
            )
        return response.json()

    def persist(
        self,
        folder: Path,
        *,
        kind: str,
        page: int,
    ) -> dict:
        archive = self.archive(folder)
        digest = hashlib.sha256(archive).hexdigest()
        path = (
            f"{REMOTE_PREFIX}"
            f"{kind}_page{page}_{digest[:24]}.zip"
        )
        self.ensure_branch()
        existing = self.lookup(path)
        if existing is None:
            blob = self.create_blob(archive)
            self.commit_entries(
                [{
                    "path": path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob,
                }],
                (
                    f"TEST save Canva snapshot "
                    f"{RUN_KEY} {kind} page {page}"
                ),
            )
            log(f"Snapshot remoto salvato: {path}")

        return {
            "branch": SNAPSHOT_BRANCH,
            "path": path,
            "sha256": digest,
            "size": len(archive),
            "page": page,
        }

    def restore(
        self,
        metadata: dict,
        destination_root: Path,
    ) -> Path:
        path = str(metadata.get("path") or "")
        expected = str(metadata.get("sha256") or "")
        if not path.startswith(REMOTE_PREFIX):
            raise RuntimeError(
                f"Snapshot fuori scope test: {path}"
            )

        info = self.lookup(path)
        if not info:
            raise FileNotFoundError(
                f"Snapshot remoto assente: {path}"
            )
        blob_sha = str(info.get("sha") or "")
        blob = self.request(
            "GET",
            f"git/blobs/{blob_sha}",
            timeout=60,
        ).json()
        if blob.get("encoding") != "base64":
            raise RuntimeError("Encoding blob inatteso")

        content = base64.b64decode(
            str(blob.get("content") or "").replace("\n", "")
        )
        digest = hashlib.sha256(content).hexdigest()
        if digest != expected:
            raise RuntimeError(
                f"SHA256 errato: {digest} != {expected}"
            )

        destination = (
            destination_root
            / f"restored_{digest[:20]}"
        )
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(
            io.BytesIO(content),
            "r",
        ) as archive:
            names = set(archive.namelist())
            if names != set(REQUIRED_SNAPSHOT_FILES):
                raise RuntimeError(
                    f"Archivio snapshot non valido: {sorted(names)}"
                )
            archive.extractall(destination)

        log(
            f"Snapshot remoto ripristinato e verificato: "
            f"{path}"
        )
        return destination

    def cleanup(self) -> int:
        if not self.enabled:
            return 0
        _, tree_sha = self.head_and_tree()
        tree = self.request(
            "GET",
            f"git/trees/{tree_sha}?recursive=1",
        ).json()
        if tree.get("truncated"):
            raise RuntimeError(
                "Tree GitHub troncato, cleanup non sicuro"
            )

        paths = [
            str(item.get("path") or "")
            for item in (tree.get("tree") or [])
            if item.get("type") == "blob"
            and str(item.get("path") or "").startswith(
                REMOTE_PREFIX
            )
        ]
        if not paths:
            return 0

        self.commit_entries(
            [{
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": None,
            } for path in paths],
            f"TEST cleanup Canva snapshots {RUN_KEY}",
        )
        log(
            f"Cleanup remoto completato: {len(paths)} file"
        )
        return len(paths)


STORE = SnapshotStore()


# =============================================================================
# TELEGRAM
# =============================================================================

def tg(
    method: str,
    *,
    data=None,
    files=None,
    timeout=25,
):
    response = bot._tg_post(
        method,
        data=data,
        files=files,
        timeout=timeout,
    )
    if response is None:
        raise RuntimeError(
            f"Telegram {method}: risposta assente"
        )
    response.raise_for_status()
    payload = response.json()
    if payload.get("ok") is False:
        raise RuntimeError(
            f"Telegram {method}: {payload}"
        )
    return payload


def send_photo(
    caption: str,
    png: bytes,
    filename: str,
) -> int:
    payload = tg(
        "sendPhoto",
        data={
            "chat_id": BOT_JR,
            "caption": caption,
            "parse_mode": "HTML",
        },
        files={
            "photo": (
                filename,
                png,
                "image/png",
            )
        },
        timeout=35,
    )
    return int(
        payload["result"]["message_id"]
    )


def edit_photo(
    message_id: int,
    caption: str,
    png: bytes,
):
    media = json.dumps({
        "type": "photo",
        "media": "attach://photo",
        "caption": caption,
        "parse_mode": "HTML",
    })
    tg(
        "editMessageMedia",
        data={
            "chat_id": BOT_JR,
            "message_id": int(message_id),
            "media": media,
        },
        files={
            "photo": (
                "kit-refresh.png",
                png,
                "image/png",
            )
        },
        timeout=35,
    )


def keyboard(mode: str, active_kit: str) -> dict:
    selected = (
        active_kit
        if mode == "manual"
        else "auto"
    )

    def button(choice: str):
        label = choice.upper()
        if choice == selected:
            label = f"✅ {label}"
        return {
            "text": label,
            "callback_data": (
                f"kit:{EVENT_ID}:{choice}"
            ),
        }

    return {
        "inline_keyboard": [[
            button("home"),
            button("away"),
            button("third"),
            button("auto"),
        ]]
    }


# =============================================================================
# TEST
# =============================================================================

class RealDynamicKitTest:
    def __init__(self):
        if not BOT_JR:
            raise RuntimeError(
                "TELEGRAM_TO_BOT assente"
            )
        if not STORE.enabled:
            raise RuntimeError(
                "Snapshot GitHub non configurati"
            )

        self.data = fetch_summary()
        (
            self.home_id,
            self.away_id,
            self.home_name,
            self.away_name,
            self.final_home,
            self.final_away,
            self.competition,
        ) = match_info(self.data)

        self.home_id = str(self.home_id)
        self.away_id = str(self.away_id)
        self.final_home = int(self.final_home)
        self.final_away = int(self.final_away)

        if str(bot.JUVE_ID) not in (
            self.home_id,
            self.away_id,
        ):
            raise RuntimeError(
                "Evento ESPN senza Juventus"
            )

        match_status, _ = bot.parse_status(self.data)
        if match_status not in ("FT", "AET", "PEN"):
            raise RuntimeError(
                f"Evento ESPN non concluso come atteso: {match_status}"
            )

        self.ht_home, self.ht_away = halftime_score(
            self.data
        )
        self.goal = real_juve_goal(self.data)

        self.fallback_kit = get_fallback_kit(
            self.data
        )
        self.espn_kit = extract_juve_uniform(
            self.data
        )
        self.mode = "auto"
        self.manual_kit = None
        self.active_kit = (
            self.espn_kit
            or self.fallback_kit
        )

        # Cross-check contro la funzione reale già presente nel bot.
        production_effective_kit = bot.rileva_kit_juve(
            self.data,
            self.home_id,
            self.away_id,
            self.home_name,
            self.away_name,
            LEAGUE_SLUG,
            LEAGUE_NAME,
        )
        if (
            production_effective_kit in VALID_KITS
            and production_effective_kit != self.active_kit
        ):
            raise RuntimeError(
                "Disallineamento kit: "
                f"runtime test={self.active_kit}, "
                f"rileva_kit_juve={production_effective_kit}"
            )

        self.page1_layers = None
        self.page2_layers = None
        self.half_remote = None
        self.full_remote = None
        self.recovery_checked = False

        self.records = {}
        self.recap_message_id = None
        self.update_offset = None
        self.processed_callbacks = set()

        self.started = None
        self.last_poll = 0.0

    def remaining(self):
        if self.started is None:
            return DURATION_SECONDS
        return max(
            0,
            int(
                DURATION_SECONDS
                - (time.monotonic() - self.started)
            ),
        )

    def recap_text(self, ended=False):
        status = "CONCLUSO" if ended else "ATTIVO"
        return (
            "🧪 <b>TEST REALE KIT DINAMICO · 5 MIN</b>\n\n"
            f"{html.escape(self.home_name)} "
            f"{self.final_home}-{self.final_away} "
            f"{html.escape(self.away_name)}\n"
            f"ESPN event: <code>{EVENT_ID}</code>\n"
            f"Stato: <b>{status}</b>\n\n"
            f"Kit ESPN reale: "
            f"<b>{display_kit(self.espn_kit)}</b>\n"
            f"Kit attivo: "
            f"<b>{display_kit(self.active_kit)}</b>\n"
            f"Modalità: <b>{self.mode.upper()}</b>\n"
            f"Fallback: "
            f"<b>{display_kit(self.fallback_kit)}</b>\n\n"
            f"HALF TIME: Canva pagina 1 · "
            f"{self.ht_home}-{self.ht_away}\n"
            f"FULL TIME: Canva pagina 2 · "
            f"{self.final_home}-{self.final_away}\n"
            f"Snapshot remoto: "
            f"{'✅' if self.half_remote and self.full_remote else '⏳'}\n"
            f"Recovery restart: "
            f"{'✅ verificato' if self.recovery_checked else '⏳'}\n"
            f"Scope remoto: <code>{RUN_KEY}</code>\n\n"
            + (
                f"Tempo residuo: ~{self.remaining()}s\n\n"
                "Premi HOME / AWAY / THIRD / AUTO. "
                "I messaggi foto devono restare gli stessi."
                if not ended
                else
                "Pulsanti rimossi e snapshot del test eliminati."
            )
        )

    def send_recap(self):
        payload = tg(
            "sendMessage",
            data={
                "chat_id": BOT_JR,
                "text": self.recap_text(),
                "parse_mode": "HTML",
                "reply_markup": json.dumps(
                    keyboard(
                        self.mode,
                        self.active_kit,
                    ),
                    ensure_ascii=False,
                ),
            },
        )
        self.recap_message_id = int(
            payload["result"]["message_id"]
        )

    def edit_recap(self, ended=False):
        if not self.recap_message_id:
            return
        data = {
            "chat_id": BOT_JR,
            "message_id": self.recap_message_id,
            "text": self.recap_text(ended=ended),
            "parse_mode": "HTML",
            "reply_markup": json.dumps(
                {"inline_keyboard": []}
                if ended
                else keyboard(
                    self.mode,
                    self.active_kit,
                ),
                ensure_ascii=False,
            ),
        }
        try:
            tg(
                "editMessageText",
                data=data,
            )
        except Exception as exc:
            if "message is not modified" not in str(exc).lower():
                log(f"Recap update fallito: {exc}")

    def drain_callbacks(self):
        payload = tg(
            "getUpdates",
            data={
                "timeout": "0",
                "allowed_updates": json.dumps(
                    ["callback_query"]
                ),
            },
            timeout=8,
        )
        updates = payload.get("result") or []
        if updates:
            self.update_offset = max(
                int(x.get("update_id", 0))
                for x in updates
            ) + 1

    def answer_callback(
        self,
        callback_id,
        text,
    ):
        try:
            tg(
                "answerCallbackQuery",
                data={
                    "callback_query_id": callback_id,
                    "text": text,
                    "show_alert": "false",
                },
                timeout=8,
            )
        except Exception as exc:
            log(
                f"answerCallbackQuery fallita: {exc}"
            )

    def poll_callbacks(self):
        data = {
            "timeout": "0",
            "allowed_updates": json.dumps(
                ["callback_query"]
            ),
        }
        if self.update_offset is not None:
            data["offset"] = str(
                self.update_offset
            )

        try:
            payload = tg(
                "getUpdates",
                data=data,
                timeout=8,
            )
        except Exception as exc:
            log(f"getUpdates fallita: {exc}")
            return

        for update in payload.get("result") or []:
            uid = int(
                update.get("update_id", 0)
            )
            self.update_offset = max(
                self.update_offset or 0,
                uid + 1,
            )

            callback = (
                update.get("callback_query")
                or {}
            )
            callback_id = str(
                callback.get("id") or ""
            )
            callback_data = str(
                callback.get("data") or ""
            )
            message = callback.get("message") or {}
            chat_id = str(
                ((message.get("chat") or {}).get("id"))
                or ""
            )

            if not callback_id:
                continue
            if chat_id and chat_id != BOT_JR:
                self.answer_callback(
                    callback_id,
                    "Messaggio non valido",
                )
                continue
            if callback_id in self.processed_callbacks:
                self.answer_callback(
                    callback_id,
                    "Già applicato",
                )
                continue

            parts = callback_data.split(":")
            if (
                len(parts) != 3
                or parts[0] != "kit"
                or parts[1] != EVENT_ID
                or parts[2] not in (
                    *VALID_KITS,
                    "auto",
                )
            ):
                self.answer_callback(
                    callback_id,
                    "Evento non attivo",
                )
                continue

            self.processed_callbacks.add(
                callback_id
            )
            choice = parts[2]
            old = self.active_kit

            if choice == "auto":
                self.mode = "auto"
                self.manual_kit = None
                self.active_kit = (
                    self.espn_kit
                    or self.fallback_kit
                )
                answer = (
                    f"AUTO · "
                    f"{display_kit(self.active_kit)}"
                )
            else:
                self.mode = "manual"
                self.manual_kit = choice
                self.active_kit = choice
                answer = (
                    f"MANUALE · "
                    f"{display_kit(self.active_kit)}"
                )

            self.answer_callback(
                callback_id,
                answer,
            )
            log(
                f"Override Bot JR: "
                f"{display_kit(old)} -> "
                f"{display_kit(self.active_kit)} "
                f"| {self.mode.upper()}"
            )

            if old != self.active_kit:
                self.refresh_all()

            self.edit_recap()

    def poll_espn(self):
        data = fetch_summary()
        self.data = data
        detected = extract_juve_uniform(
            data
        )

        old_espn = self.espn_kit
        old_active = self.active_kit

        # Mantieni l'ultimo valore ESPN valido,
        # proprio come il nuovo main.
        if detected:
            self.espn_kit = detected

        if old_espn != self.espn_kit:
            log(
                f"ESPN uniform reale: "
                f"{display_kit(old_espn)} -> "
                f"{display_kit(self.espn_kit)}"
            )

        if self.mode == "auto":
            self.active_kit = (
                self.espn_kit
                or self.fallback_kit
            )

        if old_active != self.active_kit:
            log(
                f"AUTO kit: "
                f"{display_kit(old_active)} -> "
                f"{display_kit(self.active_kit)}"
            )
            self.refresh_all()

        if (
            old_espn != self.espn_kit
            or old_active != self.active_kit
        ):
            self.edit_recap()

    # -------------------------------------------------------------------------
    # Rendering ufficiale
    # -------------------------------------------------------------------------
    def render_kick(self, kit: str) -> bytes:
        return portrait_graphics.phase(
            kind="kick",
            home_name=self.home_name,
            away_name=self.away_name,
            home_id=self.home_id,
            away_id=self.away_id,
            home_goals=0,
            away_goals=0,
            kit=kit,
            competition=LEAGUE_SLUG,
        )

    def render_half(
        self,
        kit: str,
        layers: Path,
    ) -> bytes:
        return portrait_graphics.phase(
            kind="half",
            home_name=self.home_name,
            away_name=self.away_name,
            home_id=self.home_id,
            away_id=self.away_id,
            home_goals=self.ht_home,
            away_goals=self.ht_away,
            kit=kit,
            competition=LEAGUE_SLUG,
            layers=layers,
        )

    def render_full(
        self,
        kit: str,
        layers: Path,
    ) -> bytes:
        return portrait_graphics.phase(
            kind="full",
            home_name=self.home_name,
            away_name=self.away_name,
            home_id=self.home_id,
            away_id=self.away_id,
            home_goals=self.final_home,
            away_goals=self.final_away,
            kit=kit,
            competition=LEAGUE_SLUG,
            layers=layers,
        )

    def render_goal(
        self,
        kit: str,
    ) -> bytes:
        rendered = goal_graphics.render_goal_card(
            scorer_name=self.goal["player"],
            minute=self.goal["minute"],
            home_name=self.home_name,
            away_name=self.away_name,
            home_goals=self.goal["home_goals"],
            away_goals=self.goal["away_goals"],
            kit=kit,
            goal_type=self.goal["goal_type"],
            home_id=self.home_id,
            away_id=self.away_id,
            pose=None,
            event_key=(
                f"real-test:{EVENT_ID}:"
                f"{self.goal['minute']}:"
                f"{self.goal['player']}"
            ),
            competition=LEAGUE_SLUG,
        )
        return rendered.png

    def render_stats(
        self,
        kit: str,
    ) -> bytes:
        original = bot.rileva_kit_juve
        bot.rileva_kit_juve = (
            lambda *args, **kwargs: kit
        )
        try:
            path = bot.recupera_e_genera_stats_html(
                self.data,
                self.home_id,
                self.away_id,
                self.home_name,
                self.away_name,
                self.final_home,
                self.final_away,
                "FT",
                LEAGUE_NAME,
                league_slug=LEAGUE_SLUG,
                event_id=EVENT_ID,
            )
        finally:
            bot.rileva_kit_juve = original

        if not path:
            raise RuntimeError(
                "STATS reali non generate"
            )
        return Path(path).read_bytes()

    def register(
        self,
        kind: str,
        message_id: int,
        caption: str,
        png: bytes,
        *,
        page=None,
        remote=None,
        local_layers=None,
    ):
        self.records[kind] = {
            "kind": kind,
            "message_id": int(message_id),
            "caption": caption,
            "kit": self.active_kit,
            "visual_hash": pixel_hash(png),
            "page": page,
            "remote": copy.deepcopy(remote),
            "local_layers": (
                str(local_layers)
                if local_layers
                else None
            ),
        }

    def publish_initial(self):
        log(
            f"Partita reale ESPN: "
            f"{self.home_name} "
            f"{self.final_home}-{self.final_away} "
            f"{self.away_name}"
        )
        log(
            f"Kit ESPN reale iniziale: "
            f"{display_kit(self.espn_kit)} | "
            f"active={display_kit(self.active_kit)}"
        )
        log(
            f"Gol Juventus reale dal parser produzione: "
            f"{self.goal['player']} "
            f"{self.goal['minute']} | "
            f"type={self.goal['goal_type']}"
        )

        # Canva reale. Pagina 1 e 2 vengono scaricate una volta.
        self.page1_layers = export_canva_page(1)
        self.page2_layers = export_canva_page(2)

        # Persistenza PRIMA della pubblicazione, come nel main definitivo.
        self.half_remote = STORE.persist(
            self.page1_layers,
            kind="half",
            page=1,
        )
        self.full_remote = STORE.persist(
            self.page2_layers,
            kind="full",
            page=2,
        )

        cards = []

        kick = self.render_kick(
            self.active_kit
        )
        cards.append((
            "kick",
            "🧪 <b>KICK-OFF · TEST REALE</b>",
            kick,
            {},
        ))

        goal = self.render_goal(
            self.active_kit
        )
        cards.append((
            "goal",
            (
                "🧪 <b>GOAL · TEST REALE</b>\n"
                f"{html.escape(self.goal['player'])} "
                f"{html.escape(str(self.goal['minute']))}"
            ),
            goal,
            {},
        ))

        half = self.render_half(
            self.active_kit,
            self.page1_layers,
        )
        cards.append((
            "half",
            (
                "🧪 <b>HALF TIME · CANVA PAGINA 1</b>\n"
                f"{self.ht_home}-{self.ht_away}"
            ),
            half,
            {
                "page": 1,
                "remote": self.half_remote,
                "local_layers": self.page1_layers,
            },
        ))

        full = self.render_full(
            self.active_kit,
            self.page2_layers,
        )
        cards.append((
            "full",
            (
                "🧪 <b>FULL TIME · CANVA PAGINA 2</b>\n"
                f"{self.final_home}-{self.final_away}"
            ),
            full,
            {
                "page": 2,
                "remote": self.full_remote,
                "local_layers": self.page2_layers,
            },
        ))

        stats = self.render_stats(
            self.active_kit
        )
        cards.append((
            "stats",
            "🧪 <b>STATS FT · DATI ESPN REALI</b>",
            stats,
            {},
        ))

        for kind, caption, png, extra in cards:
            message_id = send_photo(
                caption,
                png,
                f"{kind}.png",
            )
            self.register(
                kind,
                message_id,
                caption,
                png,
                **extra,
            )
            log(
                f"Pubblicato {kind} | "
                f"message_id={message_id}"
            )

        # Simula davvero la perdita del filesystem del runner.
        shutil.rmtree(
            LOCAL_CACHE,
            ignore_errors=True,
        )
        self.page1_layers = None
        self.page2_layers = None
        log(
            "SIMULAZIONE RESTART: cache Canva locale eliminata"
        )

        # Verifica subito che entrambi gli snapshot siano recuperabili.
        half_check = STORE.restore(
            self.half_remote,
            RECOVERY_CACHE / "half_check",
        )
        full_check = STORE.restore(
            self.full_remote,
            RECOVERY_CACHE / "full_check",
        )
        for folder in (half_check, full_check):
            for name in REQUIRED_SNAPSHOT_FILES:
                if not (folder / name).is_file():
                    raise RuntimeError(
                        f"Recovery incompleto: {folder / name}"
                    )
        self.recovery_checked = True
        shutil.rmtree(
            RECOVERY_CACHE,
            ignore_errors=True,
        )
        log(
            "RECOVERY CHECK OK: pagina 1 e pagina 2 "
            "ripristinate dal branch remoto"
        )

    def layers_for(self, record: dict) -> Path:
        local = record.get("local_layers")
        if local:
            path = Path(local)
            if all(
                (path / name).is_file()
                for name in REQUIRED_SNAPSHOT_FILES
            ):
                return path

        remote = record.get("remote")
        if not remote:
            raise RuntimeError(
                f"Snapshot remoto assente per {record['kind']}"
            )
        restored = STORE.restore(
            remote,
            RECOVERY_CACHE / record["kind"],
        )
        record["local_layers"] = str(restored)
        return restored

    def render_record(
        self,
        record: dict,
        kit: str,
    ) -> bytes:
        kind = record["kind"]
        if kind == "kick":
            return self.render_kick(kit)
        if kind == "goal":
            return self.render_goal(kit)
        if kind == "half":
            return self.render_half(
                kit,
                self.layers_for(record),
            )
        if kind == "full":
            return self.render_full(
                kit,
                self.layers_for(record),
            )
        if kind == "stats":
            return self.render_stats(kit)
        raise RuntimeError(
            f"Tipo non supportato: {kind}"
        )

    def refresh_all(self):
        edited = same = failed = 0

        for record in self.records.values():
            if record["kit"] == self.active_kit:
                continue

            try:
                png = self.render_record(
                    record,
                    self.active_kit,
                )
                digest = pixel_hash(png)

                if digest == record["visual_hash"]:
                    record["kit"] = self.active_kit
                    same += 1
                    log(
                        f"INVARIATA {record['kind']} | "
                        f"message_id={record['message_id']}"
                    )
                    continue

                edit_photo(
                    record["message_id"],
                    record["caption"],
                    png,
                )
                record["kit"] = self.active_kit
                record["visual_hash"] = digest
                edited += 1
                log(
                    f"MEDIA EDIT {record['kind']} | "
                    f"message_id={record['message_id']} | "
                    f"kit={self.active_kit}"
                )

            except Exception as exc:
                failed += 1
                log(
                    f"ERRORE refresh {record['kind']} | "
                    f"{type(exc).__name__}: {exc}"
                )

        log(
            f"REFRESH COMPLETO | edit={edited} "
            f"invariate={same} errori={failed}"
        )

    def run(self):
        self.drain_callbacks()
        self.send_recap()

        try:
            self.publish_initial()
            # I 5 minuti interattivi partono solo quando tutte le grafiche,
            # i due snapshot Canva e il recovery check sono pronti.
            self.started = time.monotonic()
            self.last_poll = 0.0
            self.edit_recap()
            log("FINESTRA INTERATTIVA AVVIATA: 300 secondi pieni")

            while (
                time.monotonic() - self.started
                < DURATION_SECONDS
            ):
                now = time.monotonic()

                if (
                    now - self.last_poll
                    >= POLL_SECONDS
                ):
                    self.poll_espn()
                    self.last_poll = now
                    log(
                        f"ESPN poll reale OK | "
                        f"uniform={display_kit(self.espn_kit)} | "
                        f"mode={self.mode.upper()} | "
                        f"active={display_kit(self.active_kit)}"
                    )

                self.poll_callbacks()
                time.sleep(1)

        finally:
            try:
                STORE.cleanup()
            except Exception as exc:
                log(
                    f"Cleanup remoto fallito: {exc}"
                )

            shutil.rmtree(
                LOCAL_CACHE,
                ignore_errors=True,
            )
            shutil.rmtree(
                RECOVERY_CACHE,
                ignore_errors=True,
            )

            try:
                self.edit_recap(ended=True)
            except Exception as exc:
                log(
                    f"Rimozione pulsanti fallita: {exc}"
                )

            log("TEST REALE TERMINATO")


def main() -> int:
    if DURATION_SECONDS != 300:
        log(
            f"Durata configurata: {DURATION_SECONDS}s "
            "(default richiesto: 300s)"
        )

    test = RealDynamicKitTest()
    test.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
