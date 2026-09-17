import io
import json
import os
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageOps, ImageDraw

import canva_page_oneimport json
import os
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageOps

import canva_page_one
import goal_graphics as g
import juve_bot_espn as livebot
import portrait_graphics as p

# =========================================================
# TEST DEDICATO — JUVENTUS 3-0 NEC, EUROPA LEAGUE
# =========================================================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BOT_JR_CHAT_ID = os.getenv("TELEGRAM_TO_BOT", "").strip()
CANVA_DESIGN_ID = os.getenv(
    "CANVA_DESIGN_ID",
    getattr(livebot, "CANVA_DESIGN_ID", "DAHI3ytu6yQ"),
).strip()

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
    """Verifica solo i secret già usati dal LiveScore normale."""
    required = {
        "TELEGRAM_TOKEN": BOT_TOKEN,
        "TELEGRAM_TO_BOT": BOT_JR_CHAT_ID,
        "CANVA_CLIENT_ID": os.getenv("CANVA_CLIENT_ID", "").strip(),
        "CANVA_CLIENT_SECRET": os.getenv("CANVA_CLIENT_SECRET", "").strip(),
        "CANVA_REFRESH_TOKEN": os.getenv("CANVA_REFRESH_TOKEN", "").strip(),
        # get_valid_token() salva qui un eventuale refresh token ruotato.
        "GH_PAT": os.getenv("GH_PAT", "").strip(),
        "GITHUB_REPOSITORY": os.getenv("GITHUB_REPOSITORY", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Variabili mancanti: " + ", ".join(missing) +
            "\nIl test usa gli stessi secret Canva del LiveScore principale."
        )


def export_canva_layers_once() -> Path:
    """Ottiene il token con la stessa logica del LiveScore ed esporta pagina 1 una sola volta."""
    token = livebot.get_valid_token()
    if not token:
        raise RuntimeError("Impossibile ottenere un access token Canva valido")

    session = requests.Session()
    cache_dir = Path(tempfile.mkdtemp(prefix="jr_ft_compare_canva_"))
    return canva_page_one.export_page_one(
        session,
        token,
        CANVA_DESIGN_ID,
        cache_dir,
    )


def load_logo_without_trim(
    team_name: str,
    team_id: str,
    key: str,
    assets: Path,
    canvas_height: int,
):
    """
    Carica il PNG del logo mantenendo TUTTO il canvas originale.

    Non chiama p.tight(), non calcola getbbox() e non elimina il padding alpha.
    La scala è quindi riferita al canvas completo del file sorgente.
    """
    source, origin = g.resolve_team_logo_source(team_name, str(team_id), assets)
    if source is None:
        raise g.GoalGraphicUnavailable(f"Logo non disponibile: {team_name}")

    source = source.convert("RGBA")
    if source.height <= 0:
        raise ValueError(f"Canvas logo non valido: {team_name}")

    width = max(1, round(source.width * canvas_height / source.height))
    source = source.resize((width, canvas_height), Image.Resampling.LANCZOS)

    # Mantiene la stessa resa cromatica delle grafiche attuali quando il logo
    # proviene da FCLogo, ma sempre sull'intero canvas non trimmato.
    if origin == "FCLogo":
        source = p.textured(source, key, assets, True)

    return source


def build_fulltime_variant(
    *,
    layers: Path,
    logo_mode: str,
    output_path: Path,
) -> Path:
    """
    Variante 1: small_padded  -> loghi piccolissimi, padding originale preservato.
    Variante 2: normal_padded -> dimensione attuale circa, padding originale preservato.

    Tutto il resto del Full Time resta sulla logica grafica attuale.
    """
    assets = ASSETS
    key = p.theme(KIT, COMPETITION)

    card = Image.open(
        assets / "portrait" / f"{key}_clean_1086x1448.png"
    ).convert("RGBA")
    if key == "ucl":
        card = p.vivid_background(card)

    W, H, M = p.W, p.H, p.M
    IW, IH = p.IW, p.IH

    # Stesso identico snapshot Canva per entrambe le varianti.
    bg = ImageOps.fit(
        Image.open(Path(layers) / "background.png").convert("RGBA"),
        (IW, IH),
        method=Image.Resampling.LANCZOS,
    )
    player = ImageOps.fit(
        Image.open(Path(layers) / "player.png").convert("RGBA"),
        (IW, IH),
        method=Image.Resampling.LANCZOS,
    )

    word = p.tight(Image.open(assets / "portrait" / "full.png"), True)
    word = word.resize(
        (IW - 36, round(word.height * (IW - 36) / word.width)),
        Image.Resampling.LANCZOS,
    )
    p.soft_place(
        bg,
        p.textured(word, key, assets),
        (18, 28),
        blur=12,
        opacity=0.60,
    )

    bg.alpha_composite(player)

    fade = Image.new("RGBA", bg.size)
    draw = ImageDraw.Draw(fade)
    for y in range(IH):
        draw.line(
            (0, y, IW, y),
            fill=(
                0,
                0,
                0,
                round(240 * max(0, (y - IH * 0.48) / (IH * 0.52)) ** 1.1),
            ),
        )
    bg.alpha_composite(fade)
    card.alpha_composite(bg, (M, M))

    # Punteggio identico alla grafica attuale.
    score = p.number(f"{HOME_GOALS}-{AWAY_GOALS}", 200, key, assets)
    score_y = 1220
    score_x = (W - score.width) // 2
    p.soft_place(
        card,
        score,
        (score_x, score_y - score.height // 2),
        blur=9,
        opacity=0.60,
    )

    if logo_mode == "small_padded":
        # Canvas volutamente molto piccolo, in stile riferimento inviato.
        logo_canvas_height = 58
        gap = 20
        blur = 6
        opacity = 0.55
    elif logo_mode == "normal_padded":
        # Mantiene circa l'ingombro usato oggi, ma senza tight del logo.
        logo_canvas_height = score.height
        gap = 28
        blur = 9
        opacity = 0.60
    else:
        raise ValueError(f"logo_mode non valido: {logo_mode}")

    home_logo = load_logo_without_trim(
        HOME_NAME, HOME_ID, key, assets, logo_canvas_height
    )
    away_logo = load_logo_without_trim(
        AWAY_NAME, AWAY_ID, key, assets, logo_canvas_height
    )

    # IMPORTANTISSIMO: il posizionamento usa width/height DEL CANVAS ORIGINALE
    # ridimensionato. Non vengono usati bounds dei pixel visibili.
    home_x = score_x - gap - home_logo.width
    away_x = score_x + score.width + gap
    home_y = score_y - home_logo.height // 2
    away_y = score_y - away_logo.height // 2

    p.soft_place(
        card, home_logo, (home_x, home_y), blur=blur, opacity=opacity
    )
    p.soft_place(
        card, away_logo, (away_x, away_y), blur=blur, opacity=opacity
    )

    card = p.brand(card, key, assets)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(output_path, format="PNG")
    return output_path


def send_media_group_to_botjr(items) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
    media = []
    files = {}

    for idx, item in enumerate(items):
        attach_name = f"file{idx}"
        files[attach_name] = open(item["path"], "rb")
        media.append({
            "type": "photo",
            "media": f"attach://{attach_name}",
            "caption": item["caption"],
        })

    try:
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
        for handle in files.values():
            handle.close()


def main() -> None:
    require_env()

    # Un solo export Canva: le due immagini differiscono esclusivamente
    # nella gestione/dimensione dei loghi.
    layers = export_canva_layers_once()
    out_dir = Path(tempfile.mkdtemp(prefix="jr_ft_compare_"))

    img1 = build_fulltime_variant(
        layers=layers,
        logo_mode="small_padded",
        output_path=out_dir / "juve_nec_full_01_small_padded.png",
    )
    img2 = build_fulltime_variant(
        layers=layers,
        logo_mode="normal_padded",
        output_path=out_dir / "juve_nec_full_02_normal_padded.png",
    )

    send_media_group_to_botjr([
        {
            "path": img1,
            "caption": "1/2 · Loghi piccolissimi · padding originale preservato",
        },
        {
            "path": img2,
            "caption": "2/2 · Loghi normali · padding originale preservato",
        },
    ])

    print("OK: 2 Full Time Juve-NEC inviati a Bot JR")
    print(img1)
    print(img2)


if __name__ == "__main__":
    main()

import portrait_graphics as p
import goal_graphics as g

# =========================================================
# CONFIG — test dedicato JUVE-NEC
# =========================================================
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BOT_JR_CHAT_ID = os.getenv("TELEGRAM_TO_BOT", "").strip()

# Per semplicità il file usa direttamente un access token Canva già valido.
# Se vuoi, in un secondo momento si può adattare al refresh token.
CANVA_ACCESS_TOKEN = os.getenv("CANVA_ACCESS_TOKEN", "").strip()
CANVA_DESIGN_ID = os.getenv("CANVA_DESIGN_ID", "DAHI3ytu6yQ").strip()

ASSETS = Path(g.DEFAULT_ASSET_DIR)

HOME_NAME = "Juventus"
AWAY_NAME = "NEC Nijmegen"
HOME_ID = "111"
AWAY_ID = "1515"  # per il test grafico basta anche se il resolver usa il nome

HOME_GOALS = 3
AWAY_GOALS = 0

KIT = "home"
COMPETITION = "uefa.europa"  # forza il tema UEL


# =========================================================
# HELPERS
# =========================================================
def require_env() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_TOKEN")
    if not BOT_JR_CHAT_ID:
        missing.append("TELEGRAM_TO_BOT")
    if not CANVA_ACCESS_TOKEN:
        missing.append("CANVA_ACCESS_TOKEN")
    if missing:
        raise RuntimeError(
            "Variabili mancanti: " + ", ".join(missing) +
            "\nImposta questi secrets/env prima di eseguire il file."
        )


def load_logo_without_trim(team_name: str, team_id: str, key: str, assets: Path, height: int):
    """
    Carica il logo SENZA tight()/senza eliminazione del padding trasparente.
    Mantiene il canvas originale del PNG.
    """
    source, origin = g.resolve_team_logo_source(team_name, str(team_id), assets)
    if source is None:
        return None

    source = source.convert("RGBA")
    if source.height <= 0:
        return None

    width = max(1, round(source.width * height / source.height))
    source = source.resize((width, height), Image.Resampling.LANCZOS)

    # Se il logo arriva dalla libreria FCLogo, manteniamo la stessa colorazione
    # coerente col tema, ma senza trimmare il PNG.
    if origin == "FCLogo":
        source = p.textured(source, key, assets, True)

    return source


def build_fulltime_variant(*, logo_mode: str, output_path: Path) -> Path:
    """
    Varianti richieste:
      1) small_padded  -> loghi piccolissimi, no trim, padding preservato
      2) normal_padded -> loghi normali, no trim, padding preservato

    Il resto della grafica resta il più vicino possibile al layout attuale.
    """
    assets = ASSETS
    key = p.theme(KIT, COMPETITION)

    # Base card
    card = Image.open(assets / "portrait" / f"{key}_clean_1086x1448.png").convert("RGBA")
    if key == "ucl":
        card = p.vivid_background(card)

    W, H, M = p.W, p.H, p.M
    IW, IH = p.IW, p.IH

    # Sempre pagina 1 da Canva
    session = requests.Session()
    cache_dir = Path(tempfile.mkdtemp(prefix="jr_canva_cache_"))
    layers = canva_page_one.export_page_one(
        session,
        CANVA_ACCESS_TOKEN,
        CANVA_DESIGN_ID,
        cache_dir,
    )

    bg = ImageOps.fit(
        Image.open(Path(layers) / "background.png").convert("RGBA"),
        (IW, IH),
        method=Image.Resampling.LANCZOS,
    )
    player = ImageOps.fit(
        Image.open(Path(layers) / "player.png").convert("RGBA"),
        (IW, IH),
        method=Image.Resampling.LANCZOS,
    )

    # FULL TIME in alto, come logica attuale
    word = p.tight(Image.open(assets / "portrait" / "full.png"), True)
    word = word.resize(
        (IW - 36, round(word.height * (IW - 36) / word.width)),
        Image.Resampling.LANCZOS,
    )
    p.soft_place(bg, p.textured(word, key, assets), (18, 28), blur=12, opacity=0.60)

    bg.alpha_composite(player)

    # Fade basso identico alla logica phase()
    fade = Image.new("RGBA", bg.size)
    draw = ImageDraw.Draw(fade)
    for y in range(IH):
        draw.line(
            (0, y, IW, y),
            fill=(0, 0, 0, round(240 * max(0, (y - IH * 0.48) / (IH * 0.52)) ** 1.1)),
        )
    bg.alpha_composite(fade)
    card.alpha_composite(bg, (M, M))

    # Score centrale
    score = p.number(f"{HOME_GOALS}-{AWAY_GOALS}", 200, key, assets)
    score_y = 1220
    score_x = (W - score.width) // 2
    p.soft_place(card, score, (score_x, score_y - score.height // 2), blur=9, opacity=0.60)

    if logo_mode == "small_padded":
        logo_height = 56
        gap = 18
        blur = 6
        opacity = 0.55
    elif logo_mode == "normal_padded":
        logo_height = score.height
        gap = 28
        blur = 9
        opacity = 0.60
    else:
        raise ValueError(f"logo_mode non valido: {logo_mode}")

    home_logo = load_logo_without_trim(HOME_NAME, HOME_ID, key, assets, logo_height)
    away_logo = load_logo_without_trim(AWAY_NAME, AWAY_ID, key, assets, logo_height)

    # Stessa logica geometrica attuale: uno a sinistra e uno a destra del punteggio,
    # ma usando l'intero canvas del logo senza trimmare il padding trasparente.
    if home_logo is not None:
        x = score_x - gap - home_logo.width
        y = score_y - home_logo.height // 2
        p.soft_place(card, home_logo, (x, y), blur=blur, opacity=opacity)

    if away_logo is not None:
        x = score_x + score.width + gap
        y = score_y - away_logo.height // 2
        p.soft_place(card, away_logo, (x, y), blur=blur, opacity=opacity)

    card = p.brand(card, key, assets)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    card.convert("RGB").save(output_path, format="PNG")
    return output_path


def send_media_group_to_botjr(items) -> None:
    """
    items = [
      {"path": Path(...), "caption": "..."},
      ...
    ]
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"

    media = []
    files = {}

    for idx, item in enumerate(items):
        attach_name = f"file{idx}"
        files[attach_name] = open(item["path"], "rb")
        entry = {
            "type": "photo",
            "media": f"attach://{attach_name}",
        }
        # Telegram mostra in pratica la caption del primo elemento dell'album:
        # la mettiamo comunque su entrambi per completezza.
        if item.get("caption"):
            entry["caption"] = item["caption"]
        media.append(entry)

    data = {
        "chat_id": BOT_JR_CHAT_ID,
        "media": json.dumps(media, ensure_ascii=False),
    }

    try:
        response = requests.post(url, data=data, files=files, timeout=180)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
    finally:
        for fh in files.values():
            try:
                fh.close()
            except Exception:
                pass


def main() -> None:
    require_env()

    out_dir = Path(tempfile.mkdtemp(prefix="jr_ft_compare_"))

    img1 = build_fulltime_variant(
        logo_mode="small_padded",
        output_path=out_dir / "juve_nec_full_small_padded.png",
    )

    img2 = build_fulltime_variant(
        logo_mode="normal_padded",
        output_path=out_dir / "juve_nec_full_normal_padded.png",
    )

    send_media_group_to_botjr([
        {
            "path": img1,
            "caption": "VARIANTE 1 — loghi piccolissimi, padding preservato",
        },
        {
            "path": img2,
            "caption": "VARIANTE 2 — loghi normali, padding preservato",
        },
    ])

    print("OK: inviate 2 immagini a Bot JR")
    print(str(img1))
    print(str(img2))


if __name__ == "__main__":
    main()
