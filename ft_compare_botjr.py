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
    """Carica il logo mantenendo INTEGRO il canvas PNG e il padding alpha."""
    source, origin = g.resolve_team_logo_source(team_name, str(team_id), assets)
    if source is None:
        raise RuntimeError(f"Logo non disponibile: {team_name}")

    source = source.convert("RGBA")
    if source.height <= 0:
        raise RuntimeError(f"Logo non valido: {team_name}")

    width = max(1, round(source.width * height / source.height))
    source = source.resize((width, height), Image.Resampling.LANCZOS)

    # Stessa resa cromatica del bot, ma SENZA p.tight().
    if origin == "FCLogo":
        source = p.textured(source, key, assets, True)

    return source


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


def build_variant(*, small: bool, output_path: Path) -> Path:
    card, key = build_base_card()

    score = p.number(f"{HOME_GOALS}-{AWAY_GOALS}", 200, key, ASSETS)
    score_y = 1220
    score_x = (p.W - score.width) // 2

    p.soft_place(
        card,
        score,
        (score_x, score_y - score.height // 2),
        blur=9,
        opacity=0.60,
    )

    if small:
        # Variante 1: loghi piccolissimi, padding preservato.
        logo_height = 56
        gap = 18
        blur = 6
        opacity = 0.55
    else:
        # Variante 2: dimensione attuale, padding preservato.
        logo_height = score.height
        gap = 28
        blur = 9
        opacity = 0.60

    home_logo = load_logo_without_trim(
        HOME_NAME, HOME_ID, key, ASSETS, logo_height
    )
    away_logo = load_logo_without_trim(
        AWAY_NAME, AWAY_ID, key, ASSETS, logo_height
    )

    # IMPORTANTE: nessun trim/tight sui loghi.
    # Le coordinate usano il canvas PNG completo, padding compreso.
    p.soft_place(
        card,
        home_logo,
        (
            score_x - gap - home_logo.width,
            score_y - home_logo.height // 2,
        ),
        blur=blur,
        opacity=opacity,
    )

    p.soft_place(
        card,
        away_logo,
        (
            score_x + score.width + gap,
            score_y - away_logo.height // 2,
        ),
        blur=blur,
        opacity=opacity,
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
        output_path=output_dir / "01_small_logos_padding_preserved.png",
    )
    variant_2 = build_variant(
        small=False,
        output_path=output_dir / "02_normal_logos_padding_preserved.png",
    )

    send_media_group([
        {
            "path": variant_1,
            "caption": "1/2 · LOGHI PICCOLISSIMI · padding trasparente preservato",
        },
        {
            "path": variant_2,
            "caption": "2/2 · LOGHI NORMALI · padding trasparente preservato",
        },
    ])

    print("OK: 2 varianti FT inviate a Bot JR")


if __name__ == "__main__":
    main()
