"""Test: card GOL di tutte le esultanze (home/away/third) in zip su Bot JR.

    python -m livescore.esultanze_zip [--output DIR] [--no-send]
"""
from __future__ import annotations

import argparse
import io
import os
import zipfile
from pathlib import Path

import requests
from PIL import Image

from livescore.graphics import goal

CELEBRATIONS = ("scream", "point_sky", "kiss_crest", "shush")
KITS = ("home", "away", "third")
MAX_ZIP = 45 * 1024 * 1024          # limite Telegram per i bot: 50 MB


def render_all(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for player in goal.load_players():
        for kit in KITS:
            for pose in CELEBRATIONS:
                if not goal.resolve_player_path(player, kit, pose).is_file():
                    continue
                card = goal.render_goal_card(scorer_name=player.name, minute=56, home_name="Juventus",
                                             away_name="Inter", home_goals=1, away_goals=0,
                                             kit=kit, pose=pose, event_key="test")
                path = out / f"{kit}_{pose}_{player.slug}.jpg"
                Image.open(io.BytesIO(card.png)).convert("RGB").save(path, quality=88)
                files.append(path)
                print(f"{len(files):3} {path.name}", flush=True)
    return files


def make_zips(files: list[Path], out: Path) -> list[Path]:
    zips, part, size = [], [], 0
    for f in files:
        if part and size + f.stat().st_size > MAX_ZIP:
            zips.append(part)
            part, size = [], 0
        part.append(f)
        size += f.stat().st_size
    if part:
        zips.append(part)
    paths = []
    for i, group in enumerate(zips, 1):
        name = "esultanze.zip" if len(zips) == 1 else f"esultanze_{i}di{len(zips)}.zip"
        path = out / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
            for f in group:
                z.write(f, f"{f.name.split('_', 1)[0]}/{f.name}")
        paths.append(path)
    return paths


def send(zips: list[Path], total: int) -> None:
    token, chat = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_TO_BOT"]
    for i, path in enumerate(zips, 1):
        with path.open("rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                              data={"chat_id": chat, "caption": f"🧪 TEST card esultanze ({total} card) {i}/{len(zips)}"},
                              files={"document": (path.name, fh, "application/zip")}, timeout=300)
        r.raise_for_status()
        print(f"Inviato {path.name}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=Path("esultanze_out"))
    p.add_argument("--no-send", action="store_true")
    a = p.parse_args()
    files = render_all(a.output / "card")
    zips = make_zips(files, a.output)
    print(f"{len(files)} card, zip: {[z.name for z in zips]}")
    if not a.no_send:
        send(zips, len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
