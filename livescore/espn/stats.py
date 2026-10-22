"""Statistiche di squadra ed xG da ESPN."""

import json

from livescore.core.log import log_line


def _estrai_stats_espn(data: dict) -> dict:
    raw = {"home": {}, "away": {}}

    try:
        for team_data in data.get("boxscore", {}).get("teams", []):
            side = "home" if team_data.get("homeAway") == "home" else "away"
            for s in team_data.get("statistics", []):
                key = s.get("name", "").lower()
                val = s.get("displayValue", "0")
                if key:
                    raw[side][key] = val
    except Exception as e:
        log_line("DEBUG", "ESPN", f"Parsing boxscore.teams fallito: {e}")

    try:
        for comp in data.get("header", {}).get("competitions", [{}]):
            for competitor in comp.get("competitors", []):
                side = "home" if competitor.get("homeAway") == "home" else "away"
                for s in competitor.get("statistics", []):
                    key = s.get("name", "").lower()
                    val = s.get("displayValue", s.get("value", "0"))
                    if key and key not in raw[side]:
                        raw[side][key] = str(val)
    except Exception as e:
        log_line("DEBUG", "ESPN", f"Parsing header competitors fallito: {e}")

    return raw


def _estrai_xg_mtchstatsgraph(payload: dict, home_id: str, away_id: str):
    """Estrae gli xG aggregati di entrambe le squadre da ``mtchStatsGrph``.

    ESPN espone questo dato nella pagina Team Stats, ma non nel ``summary``
    usato dal resto del bot. Le celle vengono associate tramite l'ID squadra:
    l'ordine ``teamOne``/``teamTwo`` non e garantito. ``0`` e un valore valido;
    ritorniamo ``None`` solo se il record o una delle due squadre e assente.
    """
    try:
        gamepackage = payload["page"]["content"]["gamepackage"]
        graph = gamepackage.get("mtchStatsGrph") or {}
        teams = graph.get("teams") or {}

        expected_goals = None
        for group in graph.get("stats") or []:
            for record in group.get("data") or []:
                if str(record.get("name", "")).strip().lower() == "expected goals":
                    expected_goals = record
                    break
            if expected_goals is not None:
                break

        if expected_goals is None:
            return None

        by_team_id = {}
        for team_key in ("teamOne", "teamTwo"):
            team_id = str((teams.get(team_key) or {}).get("id", ""))
            cell = expected_goals.get(team_key) or {}
            value = cell.get("value")
            display_value = cell.get("displayValue")

            # Non usare un controllo di truthiness: xG=0 e un dato reale.
            if not team_id or (value is None and display_value in (None, "")):
                continue

            numeric_value = value if value is not None else display_value
            try:
                by_team_id[team_id] = f"{float(numeric_value):.2f}"
            except (TypeError, ValueError):
                continue

        home_key = str(home_id)
        away_key = str(away_id)
        if home_key not in by_team_id or away_key not in by_team_id:
            return None

        return by_team_id[home_key], by_team_id[away_key]
    except (KeyError, TypeError, AttributeError):
        return None


def recupera_xg_espn(event_id: str, home_id: str, away_id: str):
    """Recupera gli xG dalla pagina ESPN Team Stats tramite Playwright.

    Qualsiasi errore e non bloccante: la grafica viene comunque generata senza
    la riga xG, come richiesto per le competizioni che non forniscono il dato.
    """
    if not event_id:
        log_line("DEBUG", "STATS", "Event ID assente; riga xG omessa")
        return None

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    url = f"https://www.espn.co.uk/football/team-stats/_/gameId/{event_id}"
    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1100},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
                ),
                locale="en-GB",
            )
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                # Il payload spesso e gia presente anche se una risorsa accessoria
                # mantiene aperto il caricamento fino al timeout.
                log_line("DEBUG", "STATS", "Timeout pagina Team Stats; uso il DOM disponibile")

            page.wait_for_timeout(3_000)
            marker = "window['__espnfitt__']="
            payload = None
            for script_text in page.locator("script").all_text_contents():
                marker_index = script_text.find(marker)
                if marker_index < 0:
                    continue
                json_text = script_text[marker_index + len(marker):].lstrip()
                payload, _ = json.JSONDecoder().raw_decode(json_text)
                break

            if payload is None:
                log_line("DEBUG", "STATS", "Payload ESPN Team Stats assente; riga xG omessa")
                return None

            result = _estrai_xg_mtchstatsgraph(payload, home_id, away_id)
            if result is None:
                log_line("DEBUG", "STATS", "xG non disponibili; riga omessa")
                return None

            log_line("DEBUG", "STATS", f"xG ESPN | home={result[0]} | away={result[1]}")
            return result
    except Exception as e:
        log_line("DEBUG", "STATS", f"Recupero xG ESPN fallito: {e}; riga omessa")
        return None
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
