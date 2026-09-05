"""Compositore locale delle grafiche GOAL Juventus.

Il modulo non genera e non modifica le fotografie dei calciatori: si aspetta
PNG gia scontornati nella cartella ``assets/goal_graphics/players`` e assembla
background, testi dinamici e calciatore in un PNG quadrato pronto per Telegram.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps
from team_matching import TeamIndex


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_ASSET_DIR = BASE_DIR / "assets" / "goal_graphics"
REGISTRY_PATH = BASE_DIR / "goal_players.json"
FCLOGO_CACHE_DIRNAME = "fclogo_cache"
FCLOGO_MANIFEST_FILENAME = "manifest.json"
CANVAS_SIZE = 1254

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

SAVED_THEME = {
    "accent": "#D97C30",
    "small": "#FFF0DF",
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


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    *,
    serif: bool = False,
    bold: bool = False,
    minimum: int = 24,
) -> ImageFont.FreeTypeFont:
    for size in range(start_size, minimum - 1, -2):
        font = _font(size, serif=serif, bold=bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(minimum, serif=serif, bold=bold)


def _centered_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    stroke_width: int = 0,
    stroke_fill: str | None = None,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    width = bbox[2] - bbox[0]
    draw.text(
        ((CANVAS_SIZE - width) // 2, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )


def _centered_tracked_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    tracking: int,
) -> None:
    """Disegna una riga centrata con spaziatura editoriale fra i caratteri."""
    advances = [draw.textlength(char, font=font) for char in text]
    width = sum(advances) + tracking * max(0, len(text) - 1)
    x = (CANVAS_SIZE - width) / 2
    _tracked_text(draw, x, y, text, font, fill, tracking=tracking)


def _tracked_text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    *,
    tracking: int,
) -> float:
    """Disegna testo spaziato da sinistra e restituisce la larghezza usata."""
    advances = [draw.textlength(char, font=font) for char in text]
    for char, advance in zip(text, advances):
        draw.text((round(x), y), char, font=font, fill=fill)
        x += advance + tracking
    return sum(advances) + tracking * max(0, len(text) - 1)


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
    # Un ID gia' noto e diverso impedisce un falso match soltanto per nome.
    teams = [item for item in payload["teams"] if isinstance(item, dict)
             and (not team_id or not item.get("espn_id")
                  or str(item["espn_id"]) == str(team_id))]
    item = TeamIndex(teams).match([team_name], team_id)
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


def _team_logo_layer(
    team_name: str,
    team_id: str,
    color: str,
    asset_dir: Path,
    *,
    max_size: int = 45,
) -> Image.Image | None:
    path = _local_team_logo_path(team_name, asset_dir, team_id)
    try:
        source = Image.open(path).convert("RGBA") if path else None
    except OSError:
        source = None
    is_fclogo = source is not None
    if source is None:
        source = _remote_espn_team_logo(team_id)
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


def _composite_team_logos(
    canvas: Image.Image,
    *,
    home_name: str,
    away_name: str,
    home_id: str,
    away_id: str,
    color: str,
    asset_dir: Path,
) -> None:
    """Inserisce FCLogo nel colore grafico o il fallback ESPN originale."""
    logos = [
        logo for logo in (
            _team_logo_layer(home_name, home_id, color, asset_dir),
            _team_logo_layer(away_name, away_id, color, asset_dir),
        )
        if logo is not None
    ]
    if not logos:
        return
    gap = 26
    width = sum(logo.width for logo in logos) + gap * (len(logos) - 1)
    x = (CANVAS_SIZE - width) // 2
    for logo in logos:
        y = 1040 + (45 - logo.height) // 2
        canvas.alpha_composite(logo, (x, y))
        x += logo.width + gap


def _render_event_card(
    *,
    player: Player | None,
    scorer_name: str,
    scorer_suffix: str = "",
    minute: str | int,
    home_name: str,
    away_name: str,
    home_goals: int,
    away_goals: int,
    player_kit: str,
    output_kit: str,
    background_filename: str,
    overlay_filename: str,
    texture_filename: str,
    theme: dict[str, str],
    minute_position: tuple[int, int] = (92, 82),
    preserve_overlay_detail: bool = True,
    home_id: str = "",
    away_id: str = "",
    pose: str | None = None,
    event_key: str = "",
    asset_dir: Path | str = DEFAULT_ASSET_DIR,
    registry_path: Path | str = REGISTRY_PATH,
) -> RenderedGoal:
    scorer_key = player.slug if player else normalize_name(scorer_name)
    selected_pose = choose_pose(
        f"{event_key}|{scorer_key}|{home_goals}-{away_goals}",
        requested=pose,
    )
    asset_dir = Path(asset_dir)
    background_path = asset_dir / "backgrounds" / background_filename
    front_word_path = asset_dir / "overlays" / overlay_filename
    word_texture_path = asset_dir / "word_textures" / texture_filename
    player_path = (
        resolve_player_path(player, player_kit, selected_pose, asset_dir)
        if player else None
    )

    if not background_path.is_file():
        raise GoalGraphicUnavailable(f"Background assente: {background_path}")
    if player_path is not None and not player_path.is_file():
        raise GoalGraphicUnavailable(f"PNG giocatore assente: {player_path}")
    if not front_word_path.is_file():
        raise GoalGraphicUnavailable(f"Overlay tipografico assente: {front_word_path}")

    background = Image.open(background_path).convert("RGBA")
    background = ImageOps.fit(
        background,
        (CANVAS_SIZE, CANVAS_SIZE),
        method=Image.Resampling.LANCZOS,
    )
    # Nei test e nelle installazioni precedenti il file puo ancora mancare: il
    # background resta un fallback sicuro, ma gli asset distribuiti usano le
    # mappe tessili dedicate generate per ciascuna variante.
    if word_texture_path.is_file():
        word_texture_source = Image.open(word_texture_path).convert("RGB")
    else:
        word_texture_source = background.copy()
    if player_path is not None:
        player_image = Image.open(player_path).convert("RGBA")
        if not _has_real_transparency(player_image):
            raise GoalGraphicUnavailable(
                f"PNG giocatore ancora senza trasparenza: {player_path}"
            )

        player_image = ImageOps.contain(
            player_image,
            (CANVAS_SIZE, CANVAS_SIZE),
            method=Image.Resampling.LANCZOS,
        )
        px = (CANVAS_SIZE - player_image.width) // 2
        py = CANVAS_SIZE - player_image.height
        background.alpha_composite(player_image, (px, py))

    # Sfumatura nera trasparente dietro la tipografia inferiore. Parte senza
    # stacco visibile e diventa piu intensa verso il fondo, come nella reference.
    shade = Image.new("RGBA", background.size, (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    gradient_start = 520
    panel_bottom = CANVAS_SIZE
    for y in range(gradient_start, panel_bottom):
        progress = (y - gradient_start) / (panel_bottom - gradient_start)
        alpha = int(225 * progress ** 1.12)
        shade_draw.line((64, y, CANVAS_SIZE - 64, y), fill=(0, 0, 0, alpha), width=1)
    background = Image.alpha_composite(background, shade)

    # Livello tipografico approvato, davanti al calciatore. Dal PNG prendiamo
    # esclusivamente l'alpha: il colore viene uniformato al GOAL superiore.
    front_word = Image.open(front_word_path).convert("RGBA")
    front_word = ImageOps.fit(
        front_word,
        (CANVAS_SIZE, CANVAS_SIZE),
        method=Image.Resampling.LANCZOS,
    )
    colored_word = _tint_textured_overlay(
        front_word,
        theme["accent"],
        texture_source=word_texture_source,
        preserve_source_detail=preserve_overlay_detail,
    )

    # Ombra molto morbida, appena staccata verso il basso: aumenta il contrasto
    # senza trasformare la parola in un elemento con contorno.
    shadow_alpha = colored_word.getchannel("A").filter(
        ImageFilter.GaussianBlur(radius=13)
    ).point(lambda value: round(value * 0.34))
    shadow = Image.new("RGBA", colored_word.size, (0, 0, 0, 0))
    shadow.putalpha(shadow_alpha)
    lowered_shadow = Image.new("RGBA", background.size, (0, 0, 0, 0))
    lowered_shadow.alpha_composite(shadow, (0, 102))
    background = Image.alpha_composite(background, lowered_shadow)

    lowered_word = Image.new("RGBA", background.size, (0, 0, 0, 0))
    lowered_word.alpha_composite(colored_word, (0, 92))
    background = Image.alpha_composite(background, lowered_word)
    draw = ImageDraw.Draw(background)

    minute_text = str(minute).strip().rstrip("'") + "'"
    minute_font = _font(46, bold=True)
    draw.text(
        minute_position,
        minute_text,
        font=minute_font,
        fill=theme["accent"],
    )

    _composite_team_logos(
        background,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
        color=theme["accent"],
        asset_dir=asset_dir,
    )
    draw = ImageDraw.Draw(background)

    display_name = player.name if player else html.unescape(scorer_name).strip()
    scorer = f"{display_name.upper()}{scorer_suffix}"
    scorer_font = _fit_font(draw, scorer, 850, 34, minimum=22)
    _centered_tracked_text(
        draw,
        1110,
        scorer,
        scorer_font,
        theme["small"],
        tracking=8,
    )

    output = io.BytesIO()
    background.convert("RGB").save(output, format="PNG", optimize=True)
    return RenderedGoal(
        png=output.getvalue(),
        player=player,
        scorer_name=display_name,
        kit=output_kit,
        pose=selected_pose,
        player_path=player_path,
        background_path=background_path,
    )


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
    return _render_event_card(
        player=card_player,
        scorer_name=scorer_name,
        scorer_suffix=scorer_suffix,
        minute=minute,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
        home_goals=home_goals,
        away_goals=away_goals,
        player_kit=kit,
        output_kit=kit,
        background_filename=f"{kit}.png",
        overlay_filename="front_goal.png",
        texture_filename=f"{kit}.png",
        theme=THEMES[kit],
        minute_position=(92, 82),
        preserve_overlay_detail=True,
        pose=pose,
        event_key=event_key,
        asset_dir=asset_dir,
        registry_path=registry_path,
    )


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
) -> RenderedGoal:
    player = find_player(goalkeeper_name, registry_path)
    if not player or player.role != "goalkeeper":
        raise GoalGraphicUnavailable(
            f"Portiere non presente nel registro: {goalkeeper_name!r}"
        )
    return _render_event_card(
        player=player,
        scorer_name=player.name,
        minute=minute,
        home_name=home_name,
        away_name=away_name,
        home_id=home_id,
        away_id=away_id,
        home_goals=home_goals,
        away_goals=away_goals,
        player_kit="third",
        output_kit="saved",
        background_filename="saved.png",
        overlay_filename="front_saved.png",
        texture_filename="saved.png",
        theme=SAVED_THEME,
        minute_position=(88, 116),
        preserve_overlay_detail=False,
        pose=pose,
        event_key=event_key,
        asset_dir=asset_dir,
        registry_path=registry_path,
    )


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
