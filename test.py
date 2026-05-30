import requests, json

# Metti un event_id reale — prendilo dai log del bot ("event_id=...")
EVENT_ID    = "737158"
LEAGUE_SLUG = "ita.1"

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

r = requests.get(f"{ESPN_BASE}/{LEAGUE_SLUG}/summary", params={"event": EVENT_ID}, timeout=15)
data = r.json()

# Salva tutto il JSON per analisi
with open("espn_dump.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("=== BOXSCORE TEAMS ===")
for team in data.get("boxscore", {}).get("teams", []):
    side = team.get("homeAway")
    print(f"\n--- {side} ---")
    for s in team.get("statistics", []):
        print(f"  {s.get('name')} = {s.get('displayValue')}")

print("\n=== HEADER COMPETITORS ===")
for comp in data.get("header", {}).get("competitions", [{}]):
    for c in comp.get("competitors", []):
        side = c.get("homeAway")
        print(f"\n--- {side} ---")
        for s in c.get("statistics", []):
            print(f"  {s.get('name')} = {s.get('displayValue', s.get('value'))}")

print("\n=== SCORING PLAYS ===")
for p in data.get("scoringPlays", []):
    print(f"  type={p.get('type',{}).get('text')} clock={p.get('clock',{}).get('displayValue')} team={p.get('team',{}).get('id')} participants={[x.get('athlete',{}).get('displayName') for x in p.get('participants',[])]}")

print("\n=== KEY PLAYS ===")
for p in data.get("keyPlays", []):
    print(f"  type={p.get('type',{}).get('text')} clock={p.get('clock',{}).get('displayValue')} team={p.get('team',{}).get('id')} participants={[x.get('athlete',{}).get('displayName') for x in p.get('participants',[])]}")

print("\n=== PLAYS (primi 30) ===")
for p in data.get("plays", [])[:30]:
    print(f"  type={p.get('type',{}).get('text')} clock={p.get('clock',{}).get('displayValue')} team={p.get('team',{}).get('id')} participants={[x.get('athlete',{}).get('displayName') for x in p.get('participants',[])]}")
