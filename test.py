import requests, json

EVENT_ID    = "737158"
LEAGUE_SLUG = "ita.1"
ESPN_BASE   = "https://site.api.espn.com/apis/site/v2/sports/soccer"

r    = requests.get(f"{ESPN_BASE}/{LEAGUE_SLUG}/summary", params={"event": EVENT_ID}, timeout=15)
data = r.json()

# Vediamo TUTTE le chiavi top-level
print("=== TOP LEVEL KEYS ===")
print(list(data.keys()))

# Boxscore completo
print("\n=== BOXSCORE KEYS ===")
print(list(data.get("boxscore", {}).keys()))

# Cerca sezione "plays" dentro boxscore
print("\n=== BOXSCORE PLAYS (primi 20) ===")
for p in data.get("boxscore", {}).get("plays", [])[:20]:
    print(f"  {p}")

# Cerca "timeline" o "incidents"
for key in ["timeline", "incidents", "events", "commentary", "gameStrip", "standings"]:
    val = data.get(key)
    if val is not None:
        print(f"\n=== {key.upper()} (tipo: {type(val).__name__}, len: {len(val) if hasattr(val, '__len__') else 'n/a'}) ===")
        if isinstance(val, list) and val:
            print(json.dumps(val[:3], indent=2, ensure_ascii=False))
        elif isinstance(val, dict):
            print(list(val.keys()))
