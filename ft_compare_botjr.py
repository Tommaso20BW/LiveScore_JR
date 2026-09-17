import json
import os
import tempfile
from pathlib import Path

import requests
from PIL import Image

import portrait_graphics as p
import goal_graphics as g

# =========================================================
# TEST DEDICATO JUVE-NEC
# Niente Canva: serve solo a confrontare il posizionamento loghi.
# =========================================================

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BOT_JR_CHAT_ID = os.getenv("TELEGRAM_TO_BOT", "").strip()

ASSETS = Path(g.DEFAULT_ASSET_DIR)

HOME_NAME = "Juventus"
AWAY_NAME = "NEC Nijmegen"
HOME_ID = "111"
AWAY_ID = "1515"

HOME_GOALS = 3
AWAY_GOALS = 0

KIT = "home"
COMPETITION = "uefa.europa"


# =========================================================
# BASICS
# =========================================================
def require_env() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_TOKEN")
    if not BOT_JR_CHAT_ID:
        missing.append("TELEGRAM_TO_BOT")
    if missing:
        raise RuntimeError("Variabili mancanti: " + ", ".join(missing))


def load_logo_without_trim(
    team_name: str,
    team_id: str,
    key: str,
    assets: Path,
    height: int,
):
    """Carica il logo mantenendo integro il canvas PNG e il padding alpha."""
    source, origin = g.resolve_team_logo_source(team_name, str(team_id), assets)
    if source is None:
        raise RuntimeError(f"Logo non disponibile: {team_name}")

    source = source.convert("RGBA")
    if source.height <= 0:
        raise RuntimeError(f"Logo non valido: {team_name}")

    width = max(1, round(source.width * height / source.height))
    source = source.resize((width, height), Image.Resampling.LANCZOS)

    # Stessa resa cromatica del bot, ma senza p.tight().
    if origin == "FCLogo":
        source = p.textured(source, key, assets, True)

    return source


def visible_bbox(image: Image.Image, threshold: int = 100):
    """Bounding box della parte realmente visibile del logo, senza alterare il PNG."""
    alpha = image.getchannel("A")
    box = alpha.point(lambda a: 255 if a > threshold else 0).getbbox()
    if box is None:
        raise RuntimeError("Logo senza area visibile")
    return box


def visible_metrics(image: Image.Image, threshold: int = 100) -> dict:
    """Metriche della sola area visibile utili per la centratura ottica."""
    box = visible_bbox(image, threshold)
    left, top, right, bottom = box
    width = max(1, right - left)
    height = max(1, bottom - top)

    alpha = image.getchannel("A")
    cropped = alpha.crop(box)
    mask = cropped.point(lambda a: 255 if a > threshold else 0)
    non_zero = sum(1 for px in mask.getdata() if px)
    fill_ratio = non_zero / float(width * height)

    return {
        "box": box,
        "width": width,
        "height": height,
        "fill_ratio": fill_ratio,
        # euristica della massa visiva orizzontale
        "mass": width * fill_ratio,
    }


def build_base_card() -> tuple[Image.Image, str]:
    """Grafica FT minima: background competizione + FULL TIME."""
    key = p.theme(KIT, COMPETITION)
    card = Image.open(
        ASSETS / "portrait" / f"{key}_clean_1086x1448.png"
    ).convert("RGBA")

    if key == "ucl":
        card = p.vivid_background(card)

    word = p.tight(Image.open(ASSETS / "portrait" / "full.png"), True)
    word = word.resize(
        (p.IW - 36, round(word.height * (p.IW - 36) / word.width)),
        Image.Resampling.LANCZOS,
    )
    p.soft_place(
        card,
        p.textured(word, key, ASSETS),
        (p.M + 18, p.M + 28),
        blur=12,
        opacity=0.60,
    )

    return card, key


# =========================================================
# POSITIONING
# =========================================================
def mode_settings(mode: str, score_height: int) -> dict:
    if mode == "small_canvas":
        return {"logo_height": 56, "gap": 18, "blur": 6, "opacity": 0.55}
    if mode in {"normal_canvas", "normal_visible", "normal_optical"}:
        return {"logo_height": score_height, "gap": 28, "blur": 9, "opacity": 0.60}
    if mode == "group_visible":
        return {"logo_height": score_height, "gap": 28, "blur": 9, "opacity": 0.60}
    if mode == "group_optical":
        return {"logo_height": score_height, "gap": 28, "blur": 9, "opacity": 0.60}
    if mode == "group_small_optical":
        return {"logo_height": round(score_height * 0.82), "gap": 26, "blur": 8, "opacity": 0.58}
    raise ValueError(f"mode non valido: {mode}")


def calc_fixed_score_positions(score_x, score_width, home_logo, away_logo, gap, strategy):
    """Strategie con punteggio bloccato al centro assoluto."""
    if strategy == "canvas":
        return score_x, score_x - gap - home_logo.width, score_x + score_width + gap

    home_info = visible_metrics(home_logo)
    away_info = visible_metrics(away_logo)
    home_box = home_info["box"]
    away_box = away_info["box"]

    if strategy == "visible":
        home_gap = gap
        away_gap = gap
    elif strategy == "optical":
        delta_mass = away_info["mass"] - home_info["mass"]
        correction = round(delta_mass * 0.16)
        correction = max(-14, min(14, correction))
        home_gap = max(16, gap - correction)
        away_gap = max(16, gap + correction)
    else:
        raise ValueError(f"strategy non valida: {strategy}")

    home_x = score_x - home_gap - home_box[2]
    away_x = score_x + score_width + away_gap - away_box[0]
    return score_x, home_x, away_x


def calc_group_centered_positions(score_width, home_logo, away_logo, gap, strategy):
    """Strategie con centratura del gruppo complessivo, non del solo punteggio."""
    home_info = visible_metrics(home_logo)
    away_info = visible_metrics(away_logo)
    home_box = home_info["box"]
    away_box = away_info["box"]

    if strategy == "group_visible":
        home_gap = gap
        away_gap = gap
    elif strategy == "group_optical":
        delta_mass = away_info["mass"] - home_info["mass"]
        correction = round(delta_mass * 0.24)
        correction = max(-20, min(20, correction))
        home_gap = max(16, gap - correction)
        away_gap = max(16, gap + correction)
    elif strategy == "group_small_optical":
        delta_mass = away_info["mass"] - home_info["mass"]
        correction = round(delta_mass * 0.22)
        correction = max(-18, min(18, correction))
        home_gap = max(14, gap - correction)
        away_gap = max(14, gap + correction)
    else:
        raise ValueError(f"strategy non valida: {strategy}")

    total_visible_width = home_info["width"] + home_gap + score_width + away_gap + away_info["width"]
    left_visible = round((p.W - total_visible_width) / 2)

    home_x = left_visible - home_box[0]
    score_x = left_visible + home_info["width"] + home_gap
    away_x = score_x + score_width + away_gap - away_box[0]

    return score_x, home_x, away_x


def calculate_positions(mode, score_width, score_height, home_logo, away_logo):
    settings = mode_settings(mode, score_height)
    gap = settings["gap"]
    centered_score_x = (p.W - score_width) // 2

    if mode == "small_canvas":
        score_x, home_x, away_x = calc_fixed_score_positions(
            centered_score_x, score_width, home_logo, away_logo, gap, "canvas"
        )
    elif mode == "normal_canvas":
        score_x, home_x, away_x = calc_fixed_score_positions(
            centered_score_x, score_width, home_logo, away_logo, gap, "canvas"
        )
    elif mode == "normal_visible":
        score_x, home_x, away_x = calc_fixed_score_positions(
            centered_score_x, score_width, home_logo, away_logo, gap, "visible"
        )
    elif mode == "normal_optical":
        score_x, home_x, away_x = calc_fixed_score_positions(
            centered_score_x, score_width, home_logo, away_logo, gap, "optical"
        )
    elif mode in {"group_visible", "group_optical", "group_small_optical"}:
        score_x, home_x, away_x = calc_group_centered_positions(
            score_width, home_logo, away_logo, gap, mode
        )
    else:
        raise ValueError(f"mode non valido: {mode}")

    return settings, score_x, home_x, away_x


# =========================================================
# RENDERING
# =========================================================
def build_variant(*, mode: str, output_path: Path) -> Path:
    card, key = build_base_card()

    score = p.number(f"{HOME_GOALS}-{AWAY_GOALS}", 200, key, ASSETS)
    score_y = 1220

    settings = mode_settings(mode, score.height)
    home_logo = load_logo_without_trim(HOME_NAME, HOME_ID, key, ASSETS, settings["logo_height"])
    away_logo = load_logo_without_trim(AWAY_NAME, AWAY_ID, key, ASSETS, settings["logo_height"])

    settings, score_x, home_x, away_x = calculate_positions(
        mode, score.width, score.height, home_logo, away_logo
    )

    p.soft_place(
        card,
        score,
        (score_x, score_y - score.height // 2),
        blur=9,
        opacity=0.60,
    )

    p.soft_place(
        card,
        home_logo,
        (home_x, score_y - home_logo.height // 2),
        blur=settings["blur"],
        opacity=settings["opacity"],
    )
    p.soft_place(
        card,
        away_logo,
        (away_x, score_y - away_logo.height // 2),
        blur=settings["blur"],
        opacity=settings["opacity"],
    )

    card = p.brand(card, key, ASSETS)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(output_path, format="PNG")
    return output_path


def send_media_group(items: list[dict]) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
    media = []
    files = {}

    try:
        for idx, item in enumerate(items):
            attach = f"photo{idx}"
            files[attach] = open(item["path"], "rb")
            entry = {
                "type": "photo",
                "media": f"attach://{attach}",
            }
            if item.get("caption"):
                entry["caption"] = item["caption"]
            media.append(entry)

        response = requests.post(
            url,
            data={
                "chat_id": BOT_JR_CHAT_ID,
                "media": json.dumps(media, ensure_ascii=False),
            },
            files=files,
            timeout=180,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
    finally:
        for fh in files.values():
            fh.close()


def main() -> None:
    require_env()

    output_dir = Path(tempfile.mkdtemp(prefix="jr_ft_padding_test_"))

    variants = [
        (
            "small_canvas",
            "01_small_logos_padding_preserved.png",
            "1/7 · LOGHI PICCOLISSIMI · padding trasparente preservato",
        ),
        (
            "normal_canvas",
            "02_normal_logos_padding_preserved.png",
            "2/7 · LOGHI NORMALI · padding trasparente preservato",
        ),
        (
            "normal_visible",
            "03_normal_logos_padding_visible_bounds.png",
            "3/7 · LOGHI NORMALI · padding preservato + distanze sui bordi visibili",
        ),
        (
            "normal_optical",
            "04_normal_logos_padding_optical_score_fixed.png",
            "4/7 · LOGHI NORMALI · padding preservato + centratura ottica (score fisso)",
        ),
        (
            "group_visible",
            "05_group_centered_visible.png",
            "5/7 · BLOCCO COMPLETO centrato · bordi visibili",
        ),
        (
            "group_optical",
            "06_group_centered_optical.png",
            "6/7 · BLOCCO COMPLETO centrato · correzione ottica forte",
        ),
        (
            "group_small_optical",
            "07_group_centered_small_optical.png",
            "7/7 · LOGHI LEGGERMENTE PIÙ PICCOLI · blocco centrato + correzione ottica",
        ),
    ]

    items = []
    saved_paths = []
    for mode, filename, caption in variants:
        path = build_variant(mode=mode, output_path=output_dir / filename)
        items.append({"path": path, "caption": caption})
        saved_paths.append(str(path))

    send_media_group(items)

    print("OK: inviate 7 immagini a Bot JR")
    for path in saved_paths:
        print(path)


if __name__ == "__main__":
    main()
