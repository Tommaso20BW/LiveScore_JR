"""Compositore locale delle grafiche GOAL Juventus.

Il modulo non genera e non modifica le fotografie dei calciatori: si aspetta
PNG gia scontornati nella cartella ``assets/goal_graphics/players`` e assembla
background, testi dinamici e calciatore in un PNG 3:4 pronto per Telegram.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFont, ImageOps
from team_matching import TeamIndex, normalize_team_name


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ASSET_DIR = BASE_DIR / "assets" / "goal_graphics"
REGISTRY_PATH = BASE_DIR / "goal_players.json"
FCLOGO_CACHE_DIRNAME = "fclogo_cache"
FCLOGO_MANIFEST_FILENAME = "manifest.json"

POSES = ("arms_crossed", "pointing")
KIT_FILE_PART = {
    "home": "",
    "away": "away_pink_",
    "third": "third_black_",
}
POSE_FILE_PART = {
    "arms_crossed": "pose_01_arms_crossed",
    "pointing": "pose_02_pointing",
}

THEMES = {
    "home": {
        "accent": "#FACA02",
        "small": "#F6F1E6",
    },
    "away": {
        "accent": "#ED95AE",
        "small": "#FFF2F7",
    },
    "third": {
        "accent": "#C7A852",
        "small": "#F4E9CC",
    },
}

class GoalGraphicUnavailable(RuntimeError):
    """La grafica non puo essere prodotta: il bot deve usare il testo."""


@dataclass(frozen=True)
class Player:
    name: str
    slug: str
    role: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class RenderedGoal:
    png: bytes
    player: Player | None
    scorer_name: str
    kit: str
    pose: str
    player_path: Path | None
    background_path: Path


def normalize_name(value: str) -> str:
    raw = html.unescape(str(value or "")).strip().casefold()
    raw = "".join(
        char for char in unicodedata.normalize("NFKD", raw)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def load_players(registry_path: Path | str = REGISTRY_PATH) -> tuple[Player, ...]:
    with Path(registry_path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return tuple(
        Player(
            name=item["name"],
            slug=item["slug"],
            role=item.get("role", "outfield"),
            aliases=tuple(item.get("aliases", [])),
        )
        for item in payload.get("players", [])
    )


def find_player(name: str, registry_path: Path | str = REGISTRY_PATH) -> Player | None:
    wanted = normalize_name(name)
    if not wanted:
        return None
    for player in load_players(registry_path):
        candidates = (player.name, *player.aliases)
        if wanted in {normalize_name(candidate) for candidate in candidates}:
            return player
    return None


def choose_pose(key: str, requested: str | None = None) -> str:
    if requested:
        if requested not in POSES:
            raise ValueError(f"Posa non valida: {requested}")
        return requested
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return POSES[digest[0] % len(POSES)]


def player_filename(player: Player, kit: str, pose: str) -> str:
    if pose not in POSES:
        raise ValueError(f"Posa non valida: {pose}")
    if player.role == "goalkeeper":
        return f"{player.slug}_keeper_orange_{POSE_FILE_PART[pose]}.png"
    kit = kit if kit in KIT_FILE_PART else "home"
    return f"{player.slug}_{KIT_FILE_PART[kit]}{POSE_FILE_PART[pose]}.png"


def resolve_player_path(
    player: Player,
    kit: str,
    pose: str,
    asset_dir: Path | str = DEFAULT_ASSET_DIR,
) -> Path:
    return Path(asset_dir) / "players" / player.slug / player_filename(player, kit, pose)


def _font_candidates(serif: bool, bold: bool) -> tuple[str, ...]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    if serif:
        names = ("georgiab.ttf", "Georgia Bold.ttf") if bold else ("georgia.ttf", "Georgia.ttf")
        linux = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        )
    else:
        names = ("arialbd.ttf", "Arial Bold.ttf") if bold else ("arial.ttf", "Arial.ttf")
        linux = (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        )
    return tuple(str(Path(windir) / "Fonts" / name) for name in names) + (linux,)


def _font(size: int, *, serif: bool = False, bold: bool = False) -> ImageFont.FreeTypeFont:
    for candidate in _font_candidates(serif, bold):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _has_real_transparency(image: Image.Image) -> bool:
    if "A" not in image.getbands():
        return False
    alpha_min, _ = image.getchannel("A").getextrema()
    return alpha_min < 250


def _tint_textured_overlay(
    source: Image.Image,
    color: str,
    texture_source: Image.Image | None = None,
    *,
    preserve_source_detail: bool = True,
) -> Image.Image:
    """Ricolora la sagoma esatta del PNG e vi imprime una trama tessile."""
    source = source.convert("RGBA")
    if texture_source is not None:
        fabric = ImageOps.fit(
            texture_source.convert("RGB"),
            source.size,
            method=Image.Resampling.LANCZOS,
        )
        # Le mappe sono state generate prendendo come riferimento diretto la
        # scritta superiore. Ne trasferiamo trama, luce e pieghe, ma centriamo
        # il colore sull'accento misurato della scritta in alto: in questo modo
        # la texture non rende la parola inferiore piu scura o di un'altra tinta.
        gray = ImageOps.autocontrast(ImageOps.grayscale(fabric), cutoff=1)
        histogram = gray.histogram()
        mean = sum(value * count for value, count in enumerate(histogram)) / sum(histogram)
        accent = Image.new("RGB", (1, 1), color).getpixel((0, 0))
        channels = []
        for component in accent:
            channels.append(gray.point(
                lambda value, component=component: max(
                    0,
                    min(255, round(component * (1 + 0.55 * (value - mean) / 255))),
                )
            ))
        fabric_colored = Image.merge("RGB", tuple(channels))
        if preserve_source_detail:
            # Nel GOAL conserviamo anche i segni di usura approvati nel PNG.
            textured_rgb = ImageChops.multiply(fabric_colored, source.convert("RGB"))
        else:
            # Il SAVED fornito ha un contorno scuro incorporato nei canali RGB:
            # ne usiamo soltanto l'alpha per ottenere una sagoma pulita.
            textured_rgb = fabric_colored
    else:
        base = Image.new("RGB", source.size, color)
        textured_rgb = ImageChops.multiply(base, source.convert("RGB"))
    textured = textured_rgb.convert("RGBA")
    textured.putalpha(source.getchannel("A"))
    return textured


def _logo_path_from_manifest(
    team_name: str,
    registry_path: Path,
    logo_dir: Path,
    team_id: str = "",
) -> Path | None:
    if not registry_path.is_file():
        return None
    try:
        with registry_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("teams"), list):
        return None
    # Gli alias manuali ESPN sono autorevoli; i vecchi ID automatici ignorati.
    teams = [item for item in payload["teams"] if isinstance(item, dict)]
    index = TeamIndex(teams)
    exact = index.by_name.get(normalize_team_name(team_name), set())
    if len(exact) > 1:
        return None
    item = teams[next(iter(exact))] if exact else index.match([team_name])
    if item is None:
        return None
    path = logo_dir / str(item.get("file", ""))
    return path if path.is_file() else None


def _local_team_logo_path(
    team_name: str,
    asset_dir: Path,
    team_id: str = "",
) -> Path | None:
    """Risolve gli alias ESPN verso i loghi locali provenienti da FCLogo."""
    dynamic_dir = asset_dir / "team_logos" / FCLOGO_CACHE_DIRNAME
    return _logo_path_from_manifest(
        team_name,
        dynamic_dir / FCLOGO_MANIFEST_FILENAME,
        dynamic_dir,
        team_id,
    )


def _remote_espn_team_logo(team_id: str) -> Image.Image | None:
    """Fallback per avversarie non ancora presenti nel catalogo FCLogo locale."""
    clean_id = re.sub(r"[^0-9]", "", str(team_id or ""))
    if not clean_id:
        return None
    url = f"https://a.espncdn.com/i/teamlogos/soccer/500/{clean_id}.png"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "LiveScore_JR/1.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            return Image.open(io.BytesIO(response.read())).convert("RGBA")
    except (OSError, ValueError):
        return None


def resolve_team_logo_source(
    team_name: str, team_id: str, asset_dir: Path,
) -> tuple[Image.Image | None, str]:
    """Stessa verifica per la card e per la notifica di avvio."""
    path = _local_team_logo_path(team_name, asset_dir, team_id)
    try:
        source = Image.open(path).convert("RGBA") if path else None
    except (OSError, ValueError):
        source = None
    if source is not None and source.getchannel("A").getbbox():
        return source, "FCLogo"
    source = _remote_espn_team_logo(team_id)
    if source is not None and source.getchannel("A").getbbox():
        return source, "ESPN"
    return None, "Non disponibile"


def _team_logo_layer(
    team_name: str,
    team_id: str,
    color: str,
    asset_dir: Path,
    *,
    max_size: int = 45,
) -> Image.Image | None:
    source, source_name = resolve_team_logo_source(team_name, team_id, asset_dir)
    is_fclogo = source_name == "FCLogo"
    if source is None:
        return None

    alpha = source.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return None
    if is_fclogo:
        # FCLogo è mono: conserva sagoma, fori e trasparenze, ma usa il colore
        # della scritta GOAL/SAVED.
        alpha = alpha.crop(bbox)
        logo = Image.new("RGBA", alpha.size, color)
        logo.putalpha(alpha)
    else:
        # Il fallback ESPN non è mono: mantiene i colori originali.
        logo = source.crop(bbox)
    logo.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return logo


def render_goal_card(
    *,
    scorer_name: str,
    minute: str | int,
    home_name: str,
    away_name: str,
    home_goals: int,
    away_goals: int,
    kit: str,
    goal_type: str = "goal",
    home_id: str = "",
    away_id: str = "",
    pose: str | None = None,
    event_key: str = "",
    asset_dir: Path | str = DEFAULT_ASSET_DIR,
    registry_path: Path | str = REGISTRY_PATH,
    competition: str = "",
) -> RenderedGoal:
    player = find_player(scorer_name, registry_path)
    if not html.unescape(scorer_name).strip():
        raise GoalGraphicUnavailable("Nome marcatore assente")

    # L'autogol mostra sempre la grafica senza la sagoma del calciatore. Anche
    # un marcatore non ancora presente nel registro mantiene la card completa:
    # manca soltanto il suo PNG.
    card_player = None if goal_type == "own goal" else player
    scorer_suffix = {
        "own goal": " (AUTOGOL)",
        "penalty goal": " (RIGORE)",
    }.get(goal_type, "")

    kit = kit if kit in THEMES else "home"
    # Per un eventuale gol del portiere resta il fondale nero, distinto dalla
    # grafica arancione SAVED che appartiene soltanto ai rigori parati.
    if card_player and card_player.role == "goalkeeper":
        kit = "third"
    try:
        from portrait_graphics import event
        return event(player=card_player, scorer_name=scorer_name, minute=minute,
                     home_name=home_name, away_name=away_name, home_id=home_id,
                     away_id=away_id, kit=kit, suffix=scorer_suffix,
                     competition=competition, pose=choose_pose(event_key, pose), assets=asset_dir)
    except (OSError, ValueError) as exc:
        raise GoalGraphicUnavailable(str(exc)) from exc


def render_saved_card(
    *,
    goalkeeper_name: str,
    minute: str | int,
    home_name: str,
    away_name: str,
    home_goals: int,
    away_goals: int,
    home_id: str = "",
    away_id: str = "",
    pose: str | None = None,
    event_key: str = "",
    asset_dir: Path | str = DEFAULT_ASSET_DIR,
    registry_path: Path | str = REGISTRY_PATH,
    competition: str = "",
) -> RenderedGoal:
    player = find_player(goalkeeper_name, registry_path)
    if not player or player.role != "goalkeeper":
        raise GoalGraphicUnavailable(
            f"Portiere non presente nel registro: {goalkeeper_name!r}"
        )
    try:
        from portrait_graphics import event
        return event(player=player, scorer_name=player.name, minute=minute,
                     home_name=home_name, away_name=away_name, home_id=home_id,
                     away_id=away_id, kit='third', saved=True,
                     competition=competition, pose=choose_pose(event_key, pose), assets=asset_dir)
    except (OSError, ValueError) as exc:
        raise GoalGraphicUnavailable(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera una preview GOAL o SAVED")
    parser.add_argument("--event", choices=("goal", "saved"), default="goal")
    parser.add_argument(
        "--goal-type",
        choices=("goal", "penalty goal", "own goal"),
        default="goal",
    )
    parser.add_argument("--player", required=True, help="Nome ESPN o alias del giocatore")
    parser.add_argument("--kit", choices=tuple(THEMES), default="home")
    parser.add_argument("--pose", choices=POSES)
    parser.add_argument("--minute", default="56")
    parser.add_argument("--home", default="Juventus")
    parser.add_argument("--away", default="Inter")
    parser.add_argument("--home-id", default="")
    parser.add_argument("--away-id", default="")
    parser.add_argument("--home-goals", type=int, default=1)
    parser.add_argument("--away-goals", type=int, default=0)
    parser.add_argument("--event-key", default="preview")
    parser.add_argument("--asset-dir", type=Path, default=DEFAULT_ASSET_DIR)
    parser.add_argument("--output", type=Path, default=BASE_DIR / "goal_preview.png")
    args = parser.parse_args()

    try:
        common = {
            "minute": args.minute,
            "home_name": args.home,
            "away_name": args.away,
            "home_id": args.home_id,
            "away_id": args.away_id,
            "home_goals": args.home_goals,
            "away_goals": args.away_goals,
            "pose": args.pose,
            "event_key": args.event_key,
            "asset_dir": args.asset_dir,
        }
        if args.event == "saved":
            result = render_saved_card(goalkeeper_name=args.player, **common)
        else:
            result = render_goal_card(
                scorer_name=args.player,
                kit=args.kit,
                goal_type=args.goal_type,
                **common,
            )
    except GoalGraphicUnavailable as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result.png)
    player_label = result.player.slug if result.player else "nessuna_sagoma"
    print(
        f"Preview salvata: {args.output} | giocatore={player_label} "
        f"nome={result.scorer_name} kit={result.kit} posa={result.pose}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
