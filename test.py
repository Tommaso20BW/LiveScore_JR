import os
import requests
import json
import time
import sys
import base64
import threading
from datetime import datetime

# ==============================================================================
# CONFIGURAZIONE (INVARIATA)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

JUVE_ID = 1144

# ==============================================================================
# FUNZIONI STATISTICHE
# ==============================================================================
def _fetch_stats_and_logos(fixture_id, home_id):
    headers = {"x-apisports-key": API_KEY}
    try:
        r = requests.get(f"https://v3.football.api-sports.io/fixtures/statistics", headers=headers, params={"fixture": fixture_id}, timeout=15)
        raw = r.json().get("response", [])
    except: return {}, {}, "", ""
    home_stats, away_stats, home_logo, away_logo = {}, {}, "", ""
    for block in raw:
        team = block.get("team", {})
        is_home = team.get("id") == home_id
        d = {s["type"]: s["value"] for s in block.get("statistics", [])}
        if is_home: home_stats, home_logo = d, team.get("logo", "")
        else: away_stats, away_logo = d, team.get("logo", "")
    return home_stats, away_stats, home_logo, away_logo

def _logo_to_base64(url):
    try:
        r = requests.get(url, timeout=8)
        b64 = base64.b64encode(r.content).decode()
        return f"data:image/png;base64,{b64}"
    except: return ""

def _parse_stat(val):
    try: return float(str(val).replace("%", "").replace(",", ".").strip())
    except: return 0.0

def _build_html(home_name, away_name, home_goals, away_goals, home_stats, away_stats, home_logo_b64, away_logo_b64):
    # Lista delle 11 statistiche richieste
    STATS_ROWS = [
        ("Possesso palla", "Ball Possession", "%"),
        ("Tiri totali", "Total Shots", ""),
        ("Tiri in porta", "Shots on Goal", ""),
        ("xG", "expected_goals", ""),
        ("Passaggi riusciti", "Passes accurate", ""),
        ("Corner", "Corner Kicks", ""),
        ("Duelli vinti", "Duels won", "%"),
        ("Recuperi", "Ball Recoveries", ""),
        ("Falli", "Fouls", ""),
        ("Ammoniti", "Yellow Cards", ""),
        ("Espulsi", "Red Cards", "")
    ]
    
    def fmt(v, unit):
        f = _parse_stat(v)
        return f"{int(round(f))}%" if unit == "%" else (f"{int(round(f))}" if f == int(f) else f"{f:.1f}")

    rows_html = ""
    for i, (label, key, unit) in enumerate(STATS_ROWS):
        hv, av = _parse_stat(home_stats.get(key)), _parse_stat(away_stats.get(key))
        total = hv + av if (hv + av) > 0 else 1
        hp = round(hv / total * 100)
        bg = "rgba(255,255,255,0.03)" if i % 2 == 0 else "transparent"
        rows_html += f'''<div class="stat-row" style="background:{bg}">
          <div class="val home-val">{fmt(hv, unit)}</div>
          <div class="stat-mid"><div class="stat-label">{label}</div><div class="bar-track"><div class="bar-h" style="width:{hp}%"></div><div class="bar-a" style="width:{100-hp}%"></div></div></div>
          <div class="val away-val">{fmt(av, unit)}</div>
        </div>'''

    return f"""<!DOCTYPE html><html><head><style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;600;700;800&family=Barlow+Condensed:wght@700;900&display=swap');
    * {{margin:0; padding:0; box-sizing:border-box;}}
    body {{width: 540px; background: #0b0f1e; font-family: 'Barlow', sans-serif;}}
    .card {{width: 540px; background: #0b0f1e; border-radius: 20px; overflow: hidden; border: 1px solid rgba(255,255,255,0.1);}}
    .header {{background: #0d1528; padding: 25px 28px; border-bottom: 1px solid rgba(255,255,255,0.06);}}
    .teams-row {{display: flex; align-items: center; justify-content: space-between;}}
    .logo {{width: 65px; height: 65px; object-fit: contain; display: block; margin: 0 auto 10px;}}
    .team-name {{color: #ffffff; font-weight: 700; font-size: 15px; text-align: center;}}
    .score {{color: #ffffff; font-family: 'Barlow Condensed'; font-size: 60px; font-weight: 900;}}
    .stats-body {{padding: 20px 28px;}}
    .stats-title {{color: #6070a0; font-size: 11px; font-weight: 800; text-transform: uppercase; margin-bottom: 15px; letter-spacing: 2px; text-align: center;}}
    .stat-row {{display: flex; align-items: center; padding: 10px 6px;}}
    .val {{width: 50px; font-family: 'Barlow Condensed'; font-size: 19px; font-weight: 800; color: #ffffff;}}
    .home-val {{text-align: left;}} .away-val {{text-align: right;}}
    .stat-mid {{flex: 1; padding: 0 15px; text-align: center; color: #a0aacc; font-size: 12px; font-weight: 600;}}
    .bar-track {{display: flex; height: 8px; border-radius: 4px; background: rgba(255,255,255,0.08); margin-top: 6px;}}
    .bar-h {{background: #4f9cf9; border-radius: 4px 0 0 4px;}} .bar-a {{background: #f05252; border-radius: 0 4px 4px 0;}}
    </style></head><body><div class="card">
    <div class="header"><div class="teams-row">
      <div class="team"><img src="{home_logo_b64}" class="logo"><div class="team-name">{home_name}</div></div>
      <div class="score">{home_goals} – {away_goals}</div>
      <div class="team"><img src="{away_logo_b64}" class="logo"><div class="team-name">{away_name}</div></div>
    </div></div>
    <div class="stats-body"><div class="stats-title">STATISTICHE ANALITICHE</div>{rows_html}</div>
    </div></body></html>"""

def send_stats_image(fixture_id, home_id, away_name, home_name, away_goals, home_goals, delay_seconds=120):
    def _run():
        time.sleep(delay_seconds)
        stats = _fetch_stats_and_logos(fixture_id, home_id)
        html = _build_html(home_name, away_name, home_goals, away_goals, stats[0], stats[1], _logo_to_base64(stats[2]), _logo_to_base64(stats[3]))
        with open("/tmp/stats_card.html", "w", encoding="utf-8") as f: f.write(html)
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                # 3.0x per nitidezza e altezza 1050px per contenere 11 righe
                page = browser.new_page(viewport={"width": 540, "height": 1050}, device_scale_factor=3.0)
                page.goto("file:///tmp/stats_card.html")
                page.wait_for_timeout(2500)
                page.query_selector(".card").screenshot(path="/tmp/stats_card.png", omit_background=True)
                browser.close()
            with open("/tmp/stats_card.png", "rb") as f:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": ("stats.png", f.read())})
        except Exception as e: print(f"❌ Error Playwright: {e}")
    threading.Thread(target=_run, daemon=True).start()
