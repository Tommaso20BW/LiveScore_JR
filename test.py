import requests
import json

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TEAM_ID   = "160"

LEAGUE_SLUGS = [
    "ita.1", "ita.coppa_italia", "ita.super_cup", "ita.2",
    "uefa.champions", "uefa.europa", "uefa.europa_conf", "uefa.super_cup",
    "eng.1", "eng.fa", "eng.league_cup", "eng.2",
    "esp.1", "esp.copa_del_rey", "esp.2",
    "ger.1", "fra.1", "por.1", "ned.1",
    "friendly.club",
]

from datetime import datetime, timezone, timedelta

now_utc      = datetime.now(timezone.utc)
dates_to_try = [
    (now_utc - timedelta(days=1)).strftime("%Y%m%d"),
    now_utc.strftime("%Y%m%d"),
    (now_utc + timedelta(days=1)).strftime("%Y%m%d"),
]

found = False
for date_str in dates_to_try:
    for slug in LEAGUE_SLUGS:
        try:
            r = requests.get(f"{ESPN_BASE}/{slug}/scoreboard", params={"dates": date_str}, timeout=10)
            if r.status_code != 200:
                continue
            for event in r.json().get("events", []):
                comps = event.get("competitions", [])
                if not comps:
                    continue
                competitors = comps[0].get("competitors", [])
                ids = [c.get("team", {}).get("id", "") for c in competitors]
                if TEAM_ID not in ids:
                    continue

                # Trovata — ora fetch summary
                event_id = event["id"]
                print(f"✅ Partita trovata: event_id={event_id} slug={slug} date={date_str}")

                sr = requests.get(f"{ESPN_BASE}/{slug}/summary", params={"event": event_id}, timeout=15)
                if sr.status_code != 200:
                    print(f"❌ Summary non disponibile: {sr.status_code}")
                    break

                data   = sr.json()
                comp   = data["header"]["competitions"][0]
                status = comp.get("status", {})

                state  = status.get("type", {}).get("state", "")
                desc   = status.get("type", {}).get("description", "")
                name   = status.get("type", {}).get("name", "")
                clock  = status.get("displayClock", "")
                period = status.get("period", "")
                detail = status.get("type", {}).get("detail", "")

                print("\n--- ESPN STATUS RAW ---")
                print(f"  state       : {state}")
                print(f"  description : {desc}")
                print(f"  name        : {name}")
                print(f"  detail      : {detail}")
                print(f"  displayClock: {clock}")
                print(f"  period      : {period}")
                print("\n--- FULL status JSON ---")
                print(json.dumps(status, indent=2, ensure_ascii=False))

                found = True
                break
        except Exception as e:
            print(f"⚠️ {slug} {date_str}: {e}")
        if found:
            break
    if found:
        break

if not found:
    print(f"📭 Nessuna partita trovata per TEAM_ID={TEAM_ID}")
