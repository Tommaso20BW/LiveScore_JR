"""Percorsi del progetto: un solo posto, niente `__file__` sparsi nel codice."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent

DATA_DIR = ROOT / "data"                       # JSON modificabili (squadre, leghe, giocatori, impostazioni)
SETTINGS_FILE = DATA_DIR / "settings.json"     # parametri regolabili (vedi `python -m livescore config`)
ASSETS_DIR = ROOT / "assets" / "goal_graphics"  # asset privati copiati dai workflow
TEMPLATES_DIR = PACKAGE_DIR / "graphics" / "templates"
