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
        # euristica della "massa" visiva orizzontale
        "mass": width * fill_ratio,
    }


def build_base_card() -> tuple[Image.Image, str]:
    """Grafica FT minima: background competizione + FULL TIME + score."""
    key = p.theme(KIT, COMPETITION)
    card = Image.open(
        ASSETS / "portrait" / f"{key}_clean_1086x1448.png"
    ).convert("RGBA")

    if key == "ucl":
        card = p.vivid_background(card)

    # FULL TIME come nel compositor attuale.
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


def calculate_logo_positions(
    *,
    score_x: int,
    score_width: int,
    home_logo: Image.Image,
    away_logo: Image.Image,
    gap: int,
    mode: str,
) -> tuple[int, int]:
    """
    mode:
      - canvas: usa il canvas completo del PNG (padding incluso)
      - visible: usa i bounds visibili per distanza precisa dal punteggio
      - optical: come visible + correzione ottica asimmetrica
    """
    if mode == "canvas":
        home_x = score_x - gap - home_logo.width
        away_x = score_x + score_width + gap
        return home_x, away_x

    home_info = visible_metrics(home_logo)
    away_info = visible_metrics(away_logo)
    home_box = home_info["box"]
    away_box = away_info["box"]

    if mode == "visible":
        home_gap = gap
        away_gap = gap
    elif mode == "optical":
        # Se uno stemma è molto più largo/pieno dell'altro, gli diamo più aria.
        # Il punteggio resta perfettamente al centro; modifichiamo solo i gap.
        delta_mass = away_info["mass"] - home_info["mass"]
        correction = round(delta_mass * 0.16)
        correction = max(-14, min(14, correction))
        home_gap = max(16, gap - correction)
        away_gap = max(16, gap + correction)
    else:
        raise ValueError(f"mode non valido: {mode}")

    home_x = score_x - home_gap - home_box[2]
    away_x = score_x + score_width + away_gap - away_box[0]
    return home_x, away_x


def place_variant_logos(
    *,
    card: Image.Image,
    key: str,
    score: Image.Image,
    score_x: int,
    score_y: int,
    small: bool,
    mode: str,
) -> None:
    if small:
        logo_height = 56
        gap = 18
        blur = 6
        opacity = 0.55
    else:
        logo_height = score.height
        gap = 28
        blur = 9
        opacity = 0.60

    home_logo = load_logo_without_trim(HOME_NAME, HOME_ID, key, ASSETS, logo_height)
    away_logo = load_logo_without_trim(AWAY_NAME, AWAY_ID, key, ASSETS, logo_height)

    home_x, away_x = calculate_logo_positions(
        score_x=score_x,
        score_width=score.width,
        home_logo=home_logo,
        away_logo=away_logo,
        gap=gap,
        mode=mode,
    )

    home_y = score_y - home_logo.height // 2
    away_y = score_y - away_logo.height // 2

    p.soft_place(card, home_logo, (home_x, home_y), blur=blur, opacity=opacity)
    p.soft_place(card, away_logo, (away_x, away_y), blur=blur, opacity=opacity)


def build_variant(
    *,
    small: bool,
    mode: str,
    output_path: Path,
) -> Path:
    card, key = build_base_card()

    score = p.number(f"{HOME_GOALS}-{AWAY_GOALS}", 200, key, ASSETS)
    score_y = 1220
    score_x = (p.W - score.width) // 2

    # Il punteggio resta sempre perfettamente centrato.
    p.soft_place(
        card,
        score,
        (score_x, score_y - score.height // 2),
        blur=9,
        opacity=0.60,
    )

    place_variant_logos(
        card=card,
        key=key,
        score=score,
        score_x=score_x,
        score_y=score_y,
        small=small,
        mode=mode,
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

    variant_1 = build_variant(
        small=True,
        mode="canvas",
        output_path=output_dir / "01_small_logos_padding_preserved.png",
    )
    variant_2 = build_variant(
        small=False,
        mode="canvas",
        output_path=output_dir / "02_normal_logos_padding_preserved.png",
    )
    variant_3 = build_variant(
        small=False,
        mode="visible",
        output_path=output_dir / "03_normal_logos_padding_smart_spacing.png",
    )
    variant_4 = build_variant(
        small=False,
        mode="optical",
        output_path=output_dir / "04_normal_logos_padding_optical_centering.png",
    )

    send_media_group([
        {
            "path": variant_1,
            "caption": "1/4 · LOGHI PICCOLISSIMI · padding trasparente preservato",
        },
        {
            "path": variant_2,
            "caption": "2/4 · LOGHI NORMALI · padding trasparente preservato",
        },
        {
            "path": variant_3,
            "caption": "3/4 · LOGHI NORMALI · padding preservato + distanze sui bordi visibili",
        },
        {
            "path": variant_4,
            "caption": "4/4 · LOGHI NORMALI · padding preservato + centratura ottica",
        },
    ])

    print("OK: inviate 4 immagini a Bot JR")
    print(str(variant_1))
    print(str(variant_2))
    print(str(variant_3))
    print(str(variant_4))


if __name__ == "__main__":
    main()
