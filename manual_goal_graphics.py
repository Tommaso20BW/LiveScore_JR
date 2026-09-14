"""
Manual goal graphics runner for LiveScore_JR.

What it does
------------
- Exports a chosen Canva page in PDF PRO quality
- Extracts background.png + player.png from that Canva page
- Reuses goal_graphics.py from your repository
- Lets you choose player, kit and pose (pose = Canva page to export)
- Can render one or many goal graphics in the same workflow run
- Can send the final PNGs to Bot JR, one by one or as a Telegram album

Expected repo files
-------------------
- goal_graphics.py
- juve_bot_espn.py
- requirements.txt
- assets/ ... (whatever goal_graphics.py already expects)

Example GOAL_ITEMS_JSON
-----------------------
[
  {"player":"Kenan Yildiz","kit":"home","pose_page":2},
  {"player":"Randal Kolo Muani","kit":"away","pose_page":6},
  {"player":"Francisco Conceicao","kit":"third","pose_page":10}
]

Optional item fields:
- minute: "57'"
- score: "JUV 2-1 INT"
- subtitle: "GOAL"
- competition: "Serie A"
- design_id: override Canva design id for that single item
"""

from __future__ import annotations

import hashlib
import inspect
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image


VALID_KITS = {"home", "away", "third"}


def safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip())
    return value.strip("_") or "item"


def truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def read_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def ensure_list(obj: Any) -> list[dict]:
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return obj
    raise ValueError("GOAL_ITEMS_JSON deve contenere un oggetto oppure una lista di oggetti")


def parse_items(raw: str) -> list[dict]:
    if not raw.strip():
        raise ValueError("GOAL_ITEMS_JSON è vuoto")
    data = json.loads(raw)
    items = ensure_list(data)
    normalized = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Elemento #{idx} non valido: ogni elemento deve essere un oggetto JSON")
        player = str(item.get("player", "")).strip()
        if not player:
            raise ValueError(f"Elemento #{idx}: manca 'player'")
        pose_page = item.get("pose_page", item.get("page"))
        if pose_page is None:
            raise ValueError(f"Elemento #{idx}: manca 'pose_page'")
        try:
            pose_page = int(pose_page)
        except Exception as exc:
            raise ValueError(f"Elemento #{idx}: 'pose_page' deve essere intero") from exc

        kit = str(item.get("kit", "away")).strip().lower()
        if kit not in VALID_KITS:
            raise ValueError(f"Elemento #{idx}: kit non valido '{kit}'")

        normalized.append({
            "index": idx,
            "player": player,
            "kit": kit,
            "pose_page": pose_page,
            "minute": str(item.get("minute", "")).strip(),
            "score": str(item.get("score", "")).strip(),
            "subtitle": str(item.get("subtitle", "GOAL")).strip(),
            "competition": str(item.get("competition", "")).strip(),
            "design_id": str(item.get("design_id", "")).strip(),
        })
    return normalized


def get_bot_module():
    import juve_bot_espn as bot
    return bot


def get_goal_module():
    import goal_graphics
    return goal_graphics


def get_session(bot) -> requests.Session:
    return getattr(bot, "SESSION", requests.Session())


def extract_layers_from_pdf(pdf_bytes: bytes, destination: Path) -> Path:
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if not len(doc):
            raise ValueError("PDF Canva vuoto")
        page = doc[0]
        candidates = {"background": [], "player": []}

        for xref, smask, *_ in page.get_images(full=True):
            rects = page.get_image_rects(xref)
            if len(rects) != 1:
                continue
            rect = rects[0]
            if (rect & page.rect).get_area() < page.rect.get_area() * 0.35:
                continue

            pix = pymupdf.Pixmap(doc, xref)
            if smask:
                pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, smask))
            if pix.colorspace and pix.colorspace.n != 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)

            image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
            role = "player" if smask else "background"
            candidates[role].append((image, rect))

        if any(len(v) != 1 for v in candidates.values()):
            raise ValueError(
                "Pagina Canva ambigua: attesi esattamente un background e una sagoma con maschera.\n"
                "Controlla la pagina selezionata: deve contenere la struttura standard del bot."
            )

        destination.mkdir(parents=True, exist_ok=True)
        for role, items in candidates.items():
            image, rect = items[0]
            sx, sy = 1086 / page.rect.width, 1448 / page.rect.height
            canvas = Image.new("RGBA", (1086, 1448))
            image = image.resize(
                (round(rect.width * sx), round(rect.height * sy)),
                Image.Resampling.LANCZOS,
            )
            canvas.alpha_composite(
                image,
                (
                    round((rect.x0 - page.rect.x0) * sx),
                    round((rect.y0 - page.rect.y0) * sy),
                ),
            )
            canvas.save(destination / f"{role}.png")

        (destination / "source.pdf").write_bytes(pdf_bytes)
        (destination / "manifest.json").write_text(
            json.dumps(
                {
                    "page": 1,
                    "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                    "size": [1086, 1448],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return destination


def export_canva_page_pro(session: requests.Session, access_token: str, design_id: str, page_no: int, cache_root: Path) -> Path:
    if not access_token:
        raise ValueError("Access token Canva mancante")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = session.post(
        "https://api.canva.com/rest/v1/exports",
        headers=headers,
        json={
            "design_id": design_id,
            "format": {
                "type": "pdf",
                "pages": [page_no],
                "export_quality": "pro",
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    job = response.json()
    job = job.get("job", job)
    job_id = job["id"]

    print(f"CANVA: richiesto export PDF PRO della pagina {page_no}", flush=True)

    for _ in range(60):
        time.sleep(3)
        response = session.get(
            f"https://api.canva.com/rest/v1/exports/{job_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        job = response.json()
        job = job.get("job", job)

        if job.get("status") == "failed":
            raise RuntimeError(f"Export Canva fallito per pagina {page_no}")
        if job.get("status") == "success":
            pdf_url = job["urls"][0]
            pdf_response = session.get(pdf_url, timeout=60)
            pdf_response.raise_for_status()
            pdf_bytes = pdf_response.content
            folder = f"page_{page_no}_" + hashlib.sha256(pdf_bytes).hexdigest()[:20]
            out_dir = cache_root / folder
            print(f"CANVA: PDF PRO pagina {page_no} scaricato", flush=True)
            return extract_layers_from_pdf(pdf_bytes, out_dir)

    raise TimeoutError(f"Timeout export Canva pagina {page_no}")


def find_goal_renderer(goal_graphics):
    candidates = [
        "goal",
        "render_goal",
        "build_goal_graphic",
        "make_goal_graphic",
        "create_goal_graphic",
    ]
    for name in candidates:
        fn = getattr(goal_graphics, name, None)
        if callable(fn):
            return fn, name
    raise AttributeError(
        "Nessuna funzione goal trovata in goal_graphics.py. "
        "Controlla il nome reale della funzione e aggiungilo in find_goal_renderer()."
    )


def normalize_renderer_output(result: Any) -> bytes:
    from PIL import Image as PILImage

    if isinstance(result, (bytes, bytearray)):
        return bytes(result)

    if isinstance(result, PILImage.Image):
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()

    if isinstance(result, (str, Path)):
        return Path(result).read_bytes()

    if isinstance(result, dict):
        for key in ("png_bytes", "bytes", "image_bytes"):
            if key in result and isinstance(result[key], (bytes, bytearray)):
                return bytes(result[key])
        for key in ("png_path", "path", "output_path"):
            if key in result:
                return Path(result[key]).read_bytes()

    if isinstance(result, tuple):
        for value in result:
            try:
                return normalize_renderer_output(value)
            except Exception:
                pass

    raise TypeError("Output di goal_graphics non riconosciuto")


def render_goal_png(goal_graphics, item: dict, layers_dir: Path) -> bytes:
    renderer, renderer_name = find_goal_renderer(goal_graphics)
    sig = inspect.signature(renderer)

    pool = {
        "player": item["player"],
        "player_name": item["player"],
        "name": item["player"],
        "scorer": item["player"],
        "title": item["player"],
        "kit": item["kit"],
        "competition": item["competition"],
        "minute": item["minute"],
        "score": item["score"],
        "subtitle": item["subtitle"],
        "goal_number": item["index"],
        "goal_no": item["index"],
        "goal_count": item["index"],
        "number": item["index"],
        "pose_page": item["pose_page"],
        "page": item["pose_page"],
        "layers": layers_dir,
        "layer_dir": layers_dir,
        "page_dir": layers_dir,
        "background_png": layers_dir / "background.png",
        "player_png": layers_dir / "player.png",
    }

    kwargs = {}
    missing_required = []

    for pname, param in sig.parameters.items():
        if pname in pool:
            kwargs[pname] = pool[pname]
        elif param.default is inspect._empty and param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            missing_required.append(pname)

    if missing_required:
        raise TypeError(
            f"La funzione {renderer_name} richiede parametri non coperti automaticamente: {missing_required}. "
            "Apri manual_goal_graphics.py e mappa questi nomi nel dizionario 'pool'."
        )

    print(f"GOAL_GRAPHICS: uso funzione '{renderer_name}' per {item['player']}", flush=True)
    result = renderer(**kwargs)
    return normalize_renderer_output(result)


def build_caption(item: dict) -> str:
    line1 = f"<b>{item['subtitle']}</b>"
    parts = [item["player"]]
    if item["minute"]:
        parts.append(item["minute"])
    line2 = " • ".join(parts)
    if item["score"]:
        return f"{line1}\n\n{line2}\n{item['score']}"
    return f"{line1}\n\n{line2}"


def send_album(bot, files: list[tuple[str, bytes]], captions: list[str]) -> bool:
    if not files:
        return True

    chat_id = getattr(bot, "CHAT_ID", None)
    if not getattr(bot, "BOT_TOKEN", None) or not chat_id:
        raise RuntimeError("BOT_TOKEN o CHAT_ID mancanti per l'invio Telegram")

    media = []
    tg_files = {}
    for idx, (filename, content) in enumerate(files):
        attach_name = f"photo{idx}"
        media_item = {
            "type": "photo",
            "media": f"attach://{attach_name}",
        }
        if idx == 0 and captions:
            media_item["caption"] = captions[0]
            media_item["parse_mode"] = "HTML"
        media.append(media_item)
        tg_files[attach_name] = (filename, content, "image/png")

    response = bot._tg_post(
        "sendMediaGroup",
        data={
            "chat_id": chat_id,
            "media": json.dumps(media, ensure_ascii=False),
        },
        files=tg_files,
        timeout=40,
    )
    if response is None:
        return False
    response.raise_for_status()
    return True


def main() -> None:
    bot = get_bot_module()
    goal_graphics = get_goal_module()
    session = get_session(bot)

    raw_items = read_env("GOAL_ITEMS_JSON")
    items = parse_items(raw_items)

    access_token = bot.get_valid_token()
    if not access_token:
        raise RuntimeError(
            "Impossibile ottenere access token Canva. "
            "Controlla CANVA_CLIENT_ID, CANVA_CLIENT_SECRET e CANVA_REFRESH_TOKEN."
        )

    default_design_id = read_env("GOAL_CANVA_DESIGN_ID", getattr(bot, "CANVA_DESIGN_ID", ""))
    if not default_design_id:
        raise RuntimeError("GOAL_CANVA_DESIGN_ID mancante e CANVA_DESIGN_ID non trovato in juve_bot_espn.py")

    default_competition = read_env("DEFAULT_COMPETITION", "Serie A")
    send_to_bot_jr = truthy(read_env("SEND_TO_BOT_JR", "true"), default=True)
    send_as_album = truthy(read_env("SEND_AS_ALBUM", "false"), default=False)

    cache_root = Path(".state/manual_goal_canva")
    out_dir = Path("manual_goal_output")
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[tuple[str, bytes]] = []
    captions: list[str] = []

    for item in items:
        if not item["competition"]:
            item["competition"] = default_competition

        design_id = item["design_id"] or default_design_id
        print(
            f"JOB {item['index']}: player={item['player']} kit={item['kit']} pose_page={item['pose_page']} design={design_id}",
            flush=True,
        )

        layers_dir = export_canva_page_pro(
            session=session,
            access_token=access_token,
            design_id=design_id,
            page_no=item["pose_page"],
            cache_root=cache_root,
        )

        png_bytes = render_goal_png(goal_graphics, item, layers_dir)

        filename = f"{item['index']:02d}_{safe_name(item['player'])}_{item['kit']}_page{item['pose_page']}.png"
        output_path = out_dir / filename
        output_path.write_bytes(png_bytes)
        print(f"SALVATO: {output_path}", flush=True)

        generated_files.append((filename, png_bytes))
        captions.append(build_caption(item))

        if send_to_bot_jr and not send_as_album:
            ok = bot.send_telegram_with_photo(captions[-1], png_bytes)
            if not ok:
                raise RuntimeError(f"Invio Telegram fallito per {filename}")
            print(f"TELEGRAM: inviato {filename}", flush=True)

    if send_to_bot_jr and send_as_album:
        ok = send_album(bot, generated_files, captions)
        if not ok:
            raise RuntimeError("Invio album Telegram fallito")
        print("TELEGRAM: album inviato", flush=True)

    print(f"Completato: {len(generated_files)} grafica/e", flush=True)


if __name__ == "__main__":
    main()
