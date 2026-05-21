import os
import requests
import json
import time
import sys
import base64
import threading
from datetime import datetime

# Gestione NaCl per Secrets GitHub
try:
    from nacl import encoding, public
except ImportError:
    print("⚠️ Errore: pynacl non installata.")

# ==============================================================================
# CONFIGURAZIONE (SECRETS GITHUB)
# ==============================================================================
API_KEY = os.getenv('API_KEY')
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')
CLIENT_ID = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT = os.getenv('GH_PAT')
GITHUB_REPOSITORY = os.getenv('GITHUB_REPOSITORY')

JUVE_ID = 1798 #CAMBIARE
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

# Branding & Emoji
E_BOLT, E_FLAG, E_MIC, E_BALL, E_SUB, E_UP, E_DOWN, E_RED = '⚡️', '🏁', '🎙', '⚽️', '🔄', '🔼', '🔽', '🟥'
E_END = '🔚'

LEAGUE_EMOJIS = {135: '🇮🇹', 137: '🇮🇹', 547: '🇮🇹', 2: '🇪🇺', 3: '🇪🇺', 667: '🤝'}
JUVE_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/9/99/Juventus_FC_2017_squared_icon_%28white%29.png"

# ==============================================================================
# FUNZIONI UTILI
# ==============================================================================
def get_league_emoji(league_id):
    return LEAGUE_EMOJIS.get(league_id, "⚽️")

def clean_name(name):
    annoying = ["AC ", "AS ", " US", " FC", "FC ", "A.C. ", "A.S. "]
    for w in annoying: name = name.replace(w, "")
    return " ".join(name.split())

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def build_split_scorers_text(events, home_id, away_id):
    if not events: return ""
    h_s, a_s = [], []
    for e in events:
        if e.get('type', '').lower() == 'goal' and "shootout" not in e.get('detail', '').lower():
            m_str = f"{e['time']['elapsed']}+{e['time']['extra']}" if e['time'].get('extra') else f"{e['time']['elapsed']}"
            p_n = e.get('player', {}).get('name', 'Giocatore')
            if "penalty" in e.get('detail', '').lower(): p_n += " (Rig.)"
            elif "own goal" in e.get('detail', '').lower(): p_n += " (Autogol)"
            entry = f"{m_str}’ {p_n}"
            if e.get('team', {}).get('id') == home_id: h_s.append(entry)
            else: a_s.append(entry)
    if h_s and a_s: return f"{E_BALL} <i>{', '.join(h_s)} // {', '.join(a_s)}</i>\n"
    elif h_s: return f"{E_BALL} <i>{', '.join(h_s)}</i>\n"
    elif a_s: return f"{E_BALL} <i>{', '.join(a_s)}</i>\n"
    return ""

# ==============================================================================
# GENERAZIONE STATS (SISTEMATA PER IL COLORE BLU)
# ==============================================================================
def _p_s(v):
    try: return float(str(v or 0).replace("%","").replace(",","."))
    except: return 0.0

def send_stats_image(fixture_id, home_id, away_id, h_n, a_n, h_g, a_g, moment, l_n, l_r):
    def _run():
        time.sleep(120)
        headers = {"x-apisports-key": API_KEY}
        try:
            r = requests.get(f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}", headers=headers).json()
            h_st, a_st, h_l, a_l = {}, {}, "", ""
            for b in r.get("response", []):
                tid = b["team"]["id"]
                sd = {s["type"]: s["value"] for s in b["statistics"]}
                lg = JUVE_LOGO_URL if tid == JUVE_ID else b["team"]["logo"]
                if tid == home_id: h_st, h_l = sd, lg
                else: a_st, a_l = sd, lg
            
            lbl = {"HT": "FINE PRIMO TEMPO", "FT": "FINE PARTITA"}.get(moment, "LIVE")
            
            # USO DI DOPPIE GRAFFE {{ }} PER EVITARE IL PROBLEMA DEL COLORE BLU
            html = f"""
            <!DOCTYPE html><html><head><meta charset="utf-8">
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@600;700&family=Barlow+Condensed:wght@900&display=swap');
                body {{ width: 540px; background: #0b0f1e; font-family: 'Barlow', sans-serif; color: white; margin: 0; padding: 15px; }}
                .card {{ border-radius: 20px; border: 1px solid rgba(255,255,255,0.1); background: #0b0f1e; overflow: hidden; }}
                .header {{ background: #0d1528; padding: 20px; text-align: center; }}
                .badge {{ display: inline-block; background: #f0b429; color: #0b0f1e; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 20px; text-transform: uppercase; margin-bottom: 10px; }}
                .teams {{ display: flex; align-items: center; justify-content: space-between; }}
                .logo {{ width: 55px; height: 55px; object-fit: contain; }}
                .score {{ font-family: 'Barlow Condensed'; font-size: 50px; font-weight: 900; }}
                .stat-row {{ display: flex; align-items: center; padding: 8px 20px; }}
                .stat-label {{ flex: 1; text-align: center; font-size: 11px; color: #4a5470; }}
                .val {{ width: 45px; font-family: 'Barlow Condensed'; font-size: 18px; font-weight: 700; }}
                .bar-track {{ display: flex; height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; flex: 1; margin: 0 10px; overflow: hidden; }}
                .bar-h {{ background: #4f9cf9; height: 100%; }}
                .bar-a {{ background: #f05252; height: 100%; }}
            </style></head>
            <body><div class="card"><div class="header">
                <div style="font-size:10px; color:#4a5470; margin-bottom:5px;">{l_n} · {l_r}</div>
                <div class="badge">{lbl}</div>
                <div class="teams">
                    <div style="flex:1"><img src="{h_l}" class="logo"><div>{h_n}</div></div>
                    <div class="score">{h_g} - {a_g}</div>
                    <div style="flex:1"><img src="{a_l}" class="logo"><div>{a_n}</div></div>
                </div></div>
            """
            for lab, key, unit in [("Possesso palla", "Ball Possession", "%"), ("Tiri in porta", "Shots on Goal", ""), ("xG", "expected_goals", ""), ("Corner", "Corner Kicks", ""), ("Falli", "Fouls", "")]:
                hv, av = _p_s(h_st.get(key)), _p_s(a_st.get(key))
                hp = (hv / (hv+av)*100) if (hv+av)>0 else 50
                html += f"""<div class="stat-row"><div class="val">{int(hv) if unit=="%" else hv}{unit}</div><div style="flex:1; display:flex; flex-direction:column;"><div class="stat-label">{lab}</div><div class="bar-track"><div class="bar-h" style="width:{hp}%"></div><div class="bar-a" style="width:{100-hp}%"></div></div></div><div class="val" style="text-align:right;">{int(av) if unit=="%" else av}{unit}</div></div>"""
            
            html += "</div></body></html>"
            
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 540, "height": 800})
                page.set_content(html)
                page.wait_for_timeout(1000)
                page.query_selector(".card").screenshot(path="/tmp/stats.png")
                browser.close()
            with open("/tmp/stats.png", "rb") as f:
                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": f})
        except: pass

    threading.Thread(target=_run, daemon=True).start()

# ==============================================================================
# CANVA & GITHUB
# ==============================================================================
def update_github_secret(name, value):
    if not GH_PAT or not GITHUB_REPOSITORY: return
    headers = {"Authorization": f"Bearer {GH_PAT}", "Accept": "application/vnd.github+json"}
    try:
        pk = requests.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key", headers=headers).json()
        from nacl import public, encoding
        p_k = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        sb = public.SealedBox(p_k)
        enc = base64.b64encode(sb.encrypt(value.encode("utf-8"))).decode("utf-8")
        requests.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{name}", headers=headers, json={"encrypted_value": enc, "key_id": pk["key_id"]})
    except: pass

def get_valid_token():
    try:
        res = requests.post("https://api.canva.com/rest/v1/oauth/token", data={"grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}).json()
        if "access_token" in res:
            if res.get("refresh_token") and res["refresh_token"] != CANVA_REFRESH_TOKEN:
                update_github_secret("CANVA_REFRESH_TOKEN", res["refresh_token"])
            return res["access_token"]
    except: pass
    return None

def get_canva_image(token):
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        job = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={"design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [PAGINA_TARGET]}}).json()
        jid = job.get("id")
        for _ in range(25):
            time.sleep(5)
            st = requests.get(f"https://api.canva.com/rest/v1/exports/{jid}", headers=headers).json()
            if st.get("status") == "success": return requests.get(st.get("urls")[0]).content
    except: pass
    return None

# ==============================================================================
# CICLO PARTITA
# ==============================================================================
def avvia_ciclo_partita():
    headers = {"x-apisports-key": API_KEY}
    match_id = None
    while not match_id:
        today = datetime.now().strftime('%Y-%m-%d')
        for call in [f"live=all", f"team={JUVE_ID}&date={today}", f"team={JUVE_ID}&next=1"]:
            try:
                r = requests.get(f"https://v3.football.api-sports.io/fixtures?{call}", headers=headers).json()
                for f in r.get('response', []):
                    if f['teams']['home']['id'] == JUVE_ID or f['teams']['away']['id'] == JUVE_ID:
                        match_id = f['fixture']['id']; break
                if match_id: break
            except: pass
        if not match_id: time.sleep(30)

    state = {"sent_periods": [], "goals": 0, "sent_subs": [], "sent_cards": [], "pen_count": 0}
    print(f"✅ Monitoraggio Match {match_id}")

    while True:
        try:
            r = requests.get(f"https://v3.football.api-sports.io/fixtures?id={match_id}", headers=headers).json()
            m = r['response'][0]
            status, elapsed = m['fixture']['status']['short'], m['fixture']['status']['elapsed'] or 0
            gh, ga = m['goals']['home'] or 0, m['goals']['away'] or 0
            hid, aid = m['teams']['home']['id'], m['teams']['away']['id']
            h_n = "Juventus" if hid == JUVE_ID else clean_name(m['teams']['home']['name'])
            a_n = "Juventus" if aid == JUVE_ID else clean_name(m['teams']['away']['name'])
            e_comp = get_league_emoji(m['league']['id'])
            hashtag = f"#{h_n.replace(' ','')}{a_n.replace(' ','')}"
            l_info = [m['league']['name'], m['league']['round']]

            if (status == "1H" or elapsed > 0) and "1H" not in state["sent_periods"]:
                send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{h_n} - {a_n}\n\n{e_comp} {hashtag}")
                state["sent_periods"].append("1H")
            elif status == "HT" and "HT" not in state["sent_periods"]:
                send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{h_n} {gh}-{ga} {a_n}\n\n{e_comp} {hashtag}")
                send_stats_image(match_id, hid, aid, h_n, a_n, gh, ga, "HT", *l_info)
                state["sent_periods"].append("HT")
            elif status in ["FT", "AET", "PEN"] and "FINISHED" not in state["sent_periods"]:
                time.sleep(120)
                scorers = build_split_scorers_text(m.get('events', []), hid, aid)
                txt = f"<b>FINE PARTITA {E_FLAG}</b>\n\n<b>{h_n} {gh}-{ga} {a_n}</b>\n\n{scorers}{e_comp} {hashtag}"
                tk = get_valid_token()
                img = get_canva_image(tk)
                if img: requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={"chat_id": CHAT_ID, "caption": txt, "parse_mode": "HTML"}, files={"photo": img})
                else: send_telegram(txt)
                send_stats_image(match_id, hid, aid, h_n, a_n, gh, ga, "FT", *l_info)
                state["sent_periods"].append("FINISHED")
                sys.exit(0)

            if (gh + ga) != state["goals"]:
                send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{h_n} {gh}-{ga} {a_n}\n\n{e_comp} {hashtag}")
                state["goals"] = gh + ga

            subs_by_min = {}
            for e in m.get('events', []):
                et, mi = e['type'].lower(), e['time']['elapsed']
                if et == 'subst':
                    sid = f"sub_{mi}_{e['player']['id']}"
                    if sid not in state["sent_subs"]:
                        if mi not in subs_by_min: subs_by_min[mi] = {"in": [], "out": [], "team": e['team']['id'], "ids": []}
                        subs_by_min[mi]["in"].append(e['assist']['name'])
                        subs_by_min[mi]["out"].append(e['player']['name'])
                        subs_by_min[mi]["ids"].append(sid)
                elif et == 'card' and 'red' in e['detail'].lower():
                    cid = f"red_{mi}_{e['player']['id']}"
                    if cid not in state["sent_cards"]:
                        # NUOVO FORMATO RICHIESTO PER CARTELLINO ROSSO
                        t_card = "JUVENTUS" if e['team']['id'] == JUVE_ID else clean_name(e['team']['name']).upper()
                        send_telegram(f"<b>CARTELLINO ROSSO {t_card} {E_RED}</b>\n\n{E_END} <i>{mi}' {e['player']['name']}</i>\n\n{e_comp} {hashtag}")
                        state["sent_cards"].append(cid)
            
            for m_sub, data in subs_by_min.items():
                tt = "JUVENTUS" if data["team"] == JUVE_ID else clean_name(h_n if data["team"]==hid else a_n).upper()
                send_telegram(f"<b>CAMBIO {tt} {E_SUB}</b>\n\n{E_UP} {', '.join(data['in'])}\n{E_DOWN} {', '.join(data['out'])}\n\n{e_comp} {hashtag}")
                state["sent_subs"].extend(data["ids"])
        except: pass
        time.sleep(40)

if __name__ == "__main__":
    if os.getenv('ONLY_REFRESH_TOKEN') == "true": get_valid_token()
    else: avvia_ciclo_partita()
