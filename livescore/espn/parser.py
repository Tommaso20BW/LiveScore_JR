"""Lettura dei dati ESPN: eventi, punteggio, stato partita."""


from livescore.constants import EVENT_TYPE_MAP, E_PEN_KO, E_PEN_OK, _CT_ASSIST_RX, _CT_GOAL_RX, _CT_RED_RX, _CT_YELLOW_RX
from livescore.core import text as txt
from livescore.core.log import log_line


def normalize_event_type(raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower()
    for k, v in sorted(EVENT_TYPE_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if k in low:
            return v
    return low


# ==============================================================================
# PARSE EVENTS
# ==============================================================================
def _extract_team_id_from_commentary(item: dict, home_name: str, away_name: str,
                                      home_id: str, away_id: str) -> str:
    play = item.get("play", {})
    team_name = play.get("team", {}).get("displayName", "")
    team_id   = play.get("team", {}).get("id", "")
    if team_id:
        return str(team_id)
    if team_name:
        if team_name.lower() == home_name.lower():
            return home_id
        if team_name.lower() == away_name.lower():
            return away_id
    text = item.get("text", "")
    # I testi ESPN spesso citano ENTRAMBE le squadre (es. "Goal! Juventus 1,
    # Inter 0"): controllare solo "nome in testo" attribuirebbe sempre alla
    # squadra di casa. Si attribuisce invece al nome che compare PER PRIMO.
    text_low = text.lower()
    h_pos = text_low.find(home_name.lower()) if home_name else -1
    a_pos = text_low.find(away_name.lower()) if away_name else -1
    if h_pos >= 0 and (a_pos < 0 or h_pos < a_pos):
        return home_id
    if a_pos >= 0:
        return away_id
    return ""


def parse_events(data: dict, home_name: str = "", away_name: str = "",
                 home_id: str = "", away_id: str = "") -> list:
    events    = []
    seen_ids  = set()

    def safe_minute(clock_val) -> int:
        try:
            s = str(clock_val).strip()
            if "+" in s:
                parts_plus = s.split("+")
                base  = int(float(parts_plus[0].replace("'", "").strip()))
                extra = int(float(parts_plus[1].replace("'", "").strip()))
                return base + extra
            s = s.replace("'", "").strip()
            if ":" in s:
                return int(float(s.split(":")[0]))
            return int(float(s))
        except Exception:
            return 0

    def safe_minute_disp(clock_val) -> str:
        """Preserva il formato originale ESPN per la visualizzazione (es. '45+5')."""
        try:
            s = str(clock_val).strip().replace("'", "")
            if "+" in s:
                a, b = s.split("+", 1)
                return f"{int(float(a.strip()))}+{int(float(b.strip()))}"
            if ":" in s:
                return str(int(float(s.split(":")[0])))
            return str(int(float(s)))
        except Exception:
            return str(safe_minute(clock_val))

    def extract_athlete(participants, index=0) -> str:
        try:
            athlete = participants[index].get("athlete", {})
            display = (athlete.get("displayName") or "").strip()
            short   = (athlete.get("shortName")   or "").strip()
            # Popola il cache globale: displayName -> shortName
            # (es. "Ismael Saibari" -> "I. Saibari",
            #       "Vinicius Junior" -> "Vinicius Junior")
            # cosi fmt_player sa gia la forma corretta anche per i nomi
            # estratti da testo in FONTE 0.
            if display and short:
                txt._ESPN_SHORT_NAMES[display.lower()] = short
            return display or short or ""
        except Exception:
            return ""

    def add_event(ev_type, minute, team_id, player_name, assist_name, uid, minute_disp="", period=0):
        if uid in seen_ids:
            return
        seen_ids.add(uid)
        norm = normalize_event_type(ev_type)
        if not norm:
            return
        for existing in events:
            if (existing["type"] == norm
                    and abs(existing["minute"] - minute) <= 1
                    and existing["team_id"] == str(team_id)
                    and txt._norm_name(existing["player_name"]) == txt._norm_name(player_name)):
                # Stesso evento: aggiorna con dati più completi (es. assist
                # arrivato dopo, o nome da fonte strutturata dopo fonte testuale).
                if not existing["assist_name"] and assist_name:
                    existing["assist_name"] = assist_name
                if not existing["player_name"] and player_name:
                    existing["player_name"] = player_name
                # Aggiorna minute_disp se il nuovo ha il formato recupero (contiene "+")
                if minute_disp and "+" in minute_disp and "+" not in existing.get("minute_disp", ""):
                    existing["minute_disp"] = minute_disp
                # Aggiorna period se prima non era noto (period=0/mancante)
                if period and not existing.get("period"):
                    existing["period"] = period
                return
        # Dedup specifico sostituzioni: la stessa sostituzione può arrivare da più
        # feed ESPN (commentary + keyEvents) con uid diversi, minuto leggermente
        # diverso e participant in ordine invertito (in/out scambiati). La
        # identifico dalla COPPIA di giocatori coinvolti, indipendente dall'ordine.
        # Confronto normalizzato per tollerare differenze di accenti tra le fonti.
        # IMPORTANTE: il confronto include anche il PERIODO (tempo di gioco), non
        # solo il minuto: senza questo controllo un cambio al 44' di 1° tempo e uno
        # al 45' di 2° tempo (minuti "vicini" ma tempi diversi, separati
        # dall'intervallo) venivano erroneamente considerati lo stesso evento/slot
        # e raggruppati insieme in un unico messaggio.
        if norm == "substitution":
            pair = frozenset((txt._norm_name(player_name), txt._norm_name(assist_name)))
            for existing in events:
                if (existing["type"] == "substitution"
                        and existing["team_id"] == str(team_id)
                        and existing.get("period", 0) == period
                        and abs(existing["minute"] - minute) <= 2
                        and frozenset((txt._norm_name(existing["player_name"]),
                                       txt._norm_name(existing["assist_name"]))) == pair):
                    return
        events.append({
            "type":        norm,
            "minute":      minute,
            "minute_disp": minute_disp or str(minute),
            "seq":         len(events),   # ordine cronologico ESPN — tiebreaker nel sort
            "team_id":     str(team_id),
            "player_name": player_name,
            "assist_name": assist_name,
            "uid":         uid,
            "period":      period,        # 1=1°T, 2=2°T, 3/4=supplementari, 5=rigori
        })

    # --- FONTE 0: commentary[] testo senza play strutturato (fonte veloce) ---
    # ESPN pubblica il testo commentato molto prima dei dati strutturati (play +
    # participants). Questa fonte estrae gol, cartellini gialli e rossi dal testo
    # libero appena disponibile. Il dedup normalizzato in add_event garantisce che
    # quando arrivano i dati strutturati (FONTE 1/2) l'evento non venga duplicato,
    # ma venga solo aggiornato con eventuali dati mancanti (es. assist).
    # Le sostituzioni NON vengono parsate qui: il loro testo ESPN è ambiguo riguardo
    # all'ordine in/out, e i dati strutturati arrivano comunque in tempi brevi.
    for item in data.get("commentary", []):
        if item.get("play"):
            continue  # ha già il play strutturato → gestita da FONTE 1
        text = item.get("text", "")
        if not text:
            continue
        seq        = str(item.get("sequence", ""))
        _clock_f0  = item.get("time", {}).get("displayValue", "0")
        minute     = safe_minute(_clock_f0)
        _mdisp_f0  = safe_minute_disp(_clock_f0)
        text_low = text.lower()

        try:
            # ── GOAL ──
            mg = _CT_GOAL_RX.search(text)
            if mg:
                player   = mg.group("player").strip()
                team_txt = mg.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                # Tipo gol
                if "own goal" in text_low:
                    ev_type = "own goal"
                elif "penalty" in text_low:
                    ev_type = "penalty goal"
                else:
                    ev_type = "goal"
                # Assist (può non essere ancora nel testo rapido)
                ma = _CT_ASSIST_RX.search(text)
                assist = ma.group("assist").strip() if ma else ""
                add_event(ev_type, minute, t_id, player, assist, f"txt_g_{seq}", minute_disp=_mdisp_f0)
                continue

            # ── CARTELLINO GIALLO / DOPPIO GIALLO ──
            my = _CT_YELLOW_RX.search(text)
            if my:
                player   = my.group("player").strip()
                team_txt = my.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                second   = bool(my.group("second"))
                ev_type  = "second yellow card" if second else "yellow card"
                add_event(ev_type, minute, t_id, player, "", f"txt_y_{seq}", minute_disp=_mdisp_f0)
                continue

            # ── CARTELLINO ROSSO ──
            mr = _CT_RED_RX.search(text)
            if mr:
                player   = mr.group("player").strip()
                team_txt = mr.group("team").strip()
                tl = team_txt.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id
                else:
                    t_id = ""
                add_event("red card", minute, t_id, player, "", f"txt_r_{seq}", minute_disp=_mdisp_f0)
                continue

        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing commentary testuale fallito: {e}")

    # --- FONTE 1: commentary[].play ---
    for item in data.get("commentary", []):
        play = item.get("play")
        if not play:
            continue
        try:
            ev_type = play.get("type", {}).get("text", "")
            if not ev_type:
                continue
            uid     = str(play.get("id", "")) or f"c_{item.get('sequence','')}"
            clock   = play.get("clock", {}).get("displayValue",
                       play.get("clock", {}).get("value", "0"))
            minute  = safe_minute(clock)
            _mdisp  = safe_minute_disp(clock)
            parts   = play.get("participants", [])

            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)
                assist = extract_athlete(parts, 0)
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            period_num = play.get("period", {}).get("number", 0)
            if period_num == 5:
                raw_type = play.get("type", {}).get("type", "")
                ev_low = ev_type.lower()
                if "scored" in raw_type or "scored" in ev_low:
                    ev_type = "shootout goal"
                elif "missed" in raw_type or "missed" in ev_low:
                    ev_type = "shootout miss"
                elif "saved" in raw_type or "saved" in ev_low:
                    ev_type = "shootout saved"

            team_id = _extract_team_id_from_commentary(item, home_name, away_name, home_id, away_id)
            # Calcio della lotteria senza squadra attribuibile: scartato. La
            # fonte strutturata shootout[] lo fornirà comunque con la squadra
            # giusta; tenerlo qui lo farebbe contare alla squadra sbagliata.
            if period_num == 5 and not team_id:
                continue
            add_event(ev_type, minute, team_id, player, assist, uid, minute_disp=_mdisp, period=period_num)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing commentary fallito: {e}")

    # --- FONTE 2: keyEvents[] ---
    for item in data.get("keyEvents", []):
        try:
            play    = item if "type" in item else item.get("play", item)
            ev_type = play.get("type", {}).get("text", "")
            if not ev_type:
                continue
            uid     = str(play.get("id", "")) or f"ke_{play.get('clock',{}).get('value','')}"
            clock   = play.get("clock", {}).get("displayValue",
                       play.get("clock", {}).get("value", "0"))
            minute  = safe_minute(clock)
            _mdisp  = safe_minute_disp(clock)
            parts   = play.get("participants", [])

            if normalize_event_type(ev_type) == "substitution":
                player = extract_athlete(parts, 1)
                assist = extract_athlete(parts, 0)
            else:
                player = extract_athlete(parts, 0)
                assist = extract_athlete(parts, 1)

            t_name  = play.get("team", {}).get("displayName", "")
            t_id    = play.get("team", {}).get("id", "")
            if not t_id and t_name:
                tl = t_name.lower()
                if tl == (home_name or "").lower():
                    t_id = home_id
                elif tl == (away_name or "").lower():
                    t_id = away_id

            # Periodo 5 = lotteria dei rigori. Senza questa rimappatura un calcio
            # arrivato via keyEvents diventerebbe "penalty goal" (finendo tra i
            # marcatori del risultato finale) o "penalty missed" (scatenando un
            # finto messaggio RIGORE SBAGLIATO durante la lotteria).
            period_num_ke = play.get("period", {}).get("number", 0)
            if period_num_ke == 5:
                raw_type = play.get("type", {}).get("type", "")
                ev_low = ev_type.lower()
                if "scored" in raw_type or "scored" in ev_low or "goal" in ev_low:
                    ev_type = "shootout goal"
                elif "missed" in raw_type or "missed" in ev_low or "miss" in ev_low:
                    ev_type = "shootout miss"
                elif "saved" in raw_type or "saved" in ev_low:
                    ev_type = "shootout saved"
                if not t_id:
                    continue  # calcio non attribuibile: lo fornirà shootout[]

            add_event(ev_type, minute, t_id, player, assist, uid, minute_disp=_mdisp, period=period_num_ke)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing keyEvent fallito: {e}")

    # --- FONTE 3: scoringPlays[] (fallback) ---
    for item in data.get("scoringPlays", []):
        try:
            ev_type = item.get("type", {}).get("text", "goal")
            clock   = item.get("clock", {}).get("displayValue", "0")
            minute  = safe_minute(clock)
            _mdisp  = safe_minute_disp(clock)
            team_id = item.get("team", {}).get("id", "")
            parts   = item.get("participants", [])
            player  = extract_athlete(parts, 0)
            assist  = extract_athlete(parts, 1)
            uid     = str(item.get("id", f"sp_{minute}_{player}"))
            add_event(ev_type, minute, team_id, player, assist, uid, minute_disp=_mdisp)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing scoringPlay fallito: {e}")

    # --- FONTE 4: shootout[] ---
    for team_shootout in data.get("shootout", []):
        try:
            t_id_raw = str(team_shootout.get("id", ""))
            t_name   = team_shootout.get("team", "")
            if t_id_raw:
                t_id = t_id_raw
            elif isinstance(t_name, str) and t_name:
                t_id = home_id if t_name.lower() == home_name.lower() else away_id
            else:
                t_id = ""
            kicks = team_shootout.get("shots") or team_shootout.get("shootoutAttempts", [])
            for kick in kicks:
                did_score = kick.get("didScore", kick.get("scored", False))
                saved     = kick.get("saved", False)
                player    = kick.get("player") or kick.get("athlete", {}).get("displayName", "")
                uid       = str(kick.get("id", f"shootout_{t_id}_{player}"))
                if did_score:
                    ev_type = "shootout goal"
                elif saved:
                    ev_type = "shootout saved"
                else:
                    ev_type = "shootout miss"
                add_event(ev_type, 120, t_id, player, "", uid)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Parsing shootout fallito: {e}")

    return events


def parse_score(competitors):
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
    return (
        home.get("team", {}).get("id", ""),
        away.get("team", {}).get("id", ""),
        home.get("team", {}).get("displayName", "Home"),
        away.get("team", {}).get("displayName", "Away"),
        int(home.get("score", 0) or 0),
        int(away.get("score", 0) or 0),
    )


def parse_status(data: dict):
    try:
        comp   = data["header"]["competitions"][0]
        status = comp.get("status", {})
        stype  = status.get("type", {})
        state  = stype.get("state", "pre")
        name   = stype.get("name", "").upper()
        desc   = stype.get("description", "").lower()
        clock  = status.get("displayClock", "0:00")
        period = status.get("period", 1)

        try:
            raw_clock = clock.replace("'", "").split("+")[0].split(":")[0].strip()
            elapsed = int(raw_clock)
        except Exception:
            elapsed = 0

        if state == "pre":
            return "NS", 0

        if state == "post":
            if "PEN" in name:
                return "PEN", 120
            if "AET" in name or "EXTRA" in name:
                return "AET", 120
            return "FT", 90

        # NB: HT_ET va controllato PRIMA dell'intervallo generico, perché
        # "STATUS_HALFTIME_ET" contiene anche la sottostringa "HALFTIME" e
        # verrebbe altrimenti scambiato per l'intervallo dei tempi regolamentari.
        if "EXTRA_TIME_HALF" in name or "HALFTIME_ET" in name:
            return "HT_ET", 105
        if "HALFTIME" in name or "HALF_TIME" in name:
            # Intervallo generico: il periodo distingue quale dei due è.
            if period >= 3:
                return "HT_ET", 105
            return "HT", 45
        if "PENALTY" in name or "SHOOTOUT" in name:
            return "PEN", elapsed
        # Pausa tra fine supplementari e rigori (es. STATUS_END_OF_EXTRATIME).
        # Va controllata PRIMA del check generico "EXTRA" qui sotto, altrimenti
        # verrebbe mappata a "ET" e il bot crederebbe che si stia ancora giocando.
        if "END_OF_EXTRATIME" in name or "END_EXTRA" in name:
            return "BREAK_PEN", 120
        # Pausa tra fine regolamentari e inizio supplementari.
        if "END_OF_REGULATION" in name:
            return "BREAK_ET", 90
        if "EXTRA" in name or "OT" in name:
            return "ET", elapsed
        if "END_PERIOD" in name:
            # END_PERIOD è generico: il periodo dice QUALE pausa è.
            if period <= 1:
                return "HT", 45          # fine 1° tempo
            if period == 2:
                return "BREAK_ET", 90    # fine regolamentari (pausa pre-supplementari)
            if period == 3:
                return "HT_ET", 105      # intervallo tra i due supplementari
            return "BREAK_PEN", 120      # fine supplementari (pausa pre-rigori)
        if period == 1:
            return "1H", elapsed
        if period == 2:
            return "2H", elapsed
        if period == 3:
            return "ET", elapsed
        if period == 4:
            return "ET", elapsed

        return "1H", elapsed
    except Exception as e:
        log_line("WARN", "ESPN", f"Parsing stato partita fallito: {e}")
        return "NS", 0


def _rigori_icone(data: dict, events: list, home_id: str, away_id: str,
                  home_name_raw: str = "", away_name_raw: str = ""):
    """Restituisce (home_icons, away_icons) della lotteria dei rigori.

    Preferisce data['shootout'] (fonte strutturata ESPN): è ordinata per
    battuta e attribuisce ogni calcio alla squadra giusta. Solo se assente
    ricade sugli eventi parsati, scartando i calci senza squadra attribuita
    (che altrimenti finirebbero per errore nel conteggio della trasferta).
    """
    home_icons, away_icons = [], []

    for team_shootout in (data.get("shootout") or []):
        try:
            t_id_raw = str(team_shootout.get("id", ""))
            t_name   = team_shootout.get("team", "")
            if t_id_raw:
                t_id = t_id_raw
            elif isinstance(t_name, str) and t_name:
                t_id = home_id if t_name.lower() == (home_name_raw or "").lower() else away_id
            else:
                continue
            if t_id == str(home_id):
                target = home_icons
            elif t_id == str(away_id):
                target = away_icons
            else:
                continue
            for kick in (team_shootout.get("shots") or team_shootout.get("shootoutAttempts", [])):
                did_score = kick.get("didScore", kick.get("scored", False))
                target.append(E_PEN_OK if did_score else E_PEN_KO)
        except Exception as e:
            log_line("DEBUG", "ESPN", f"Lettura shootout strutturato fallita: {e}")

    if home_icons or away_icons:
        return home_icons, away_icons

    # Fallback: eventi parsati (commentary/keyEvents), in ordine di arrivo (seq)
    for e in sorted(events, key=lambda x: x.get("seq", 0)):
        if e["type"] not in ("shootout goal", "shootout miss", "shootout saved"):
            continue
        icon = E_PEN_OK if e["type"] == "shootout goal" else E_PEN_KO
        if e["team_id"] == str(home_id):
            home_icons.append(icon)
        elif e["team_id"] == str(away_id):
            away_icons.append(icon)
        # team_id sconosciuto → scartato: meglio un calcio in meno nel widget
        # che un calcio assegnato alla squadra sbagliata.
    return home_icons, away_icons


def _shootout_deciso(home_icons: list, away_icons: list) -> bool:
    """True se la lotteria dei rigori è matematicamente decisa, anche se
    ESPN non ha ancora aggiornato status.type.state a 'post' (può volerci
    diversi minuti dopo l'ultimo tiro — visto un ritardo di 7' su Svizzera-
    Colombia 2026: rigore decisivo segnato ma state ancora 'in').

    NB sui conteggi disuguali: quando a chiudere è la squadra che batte per
    PRIMA, l'ultimo tiro dell'altra non si batte proprio e i conteggi restano
    disuguali per sempre (es. 5 tiri vs 4). Va quindi accettato uno sbilancio
    di 1 tiro; oltre 1 il feed è incompleto e non ci si può fidare della
    matematica (tiri mancanti → falsi positivi)."""
    n_home, n_away = len(home_icons), len(away_icons)
    if n_home == 0 and n_away == 0:
        return False
    if abs(n_home - n_away) > 1:
        return False  # feed incompleto: mancano tiri, matematica inaffidabile
    home_goals = home_icons.count(E_PEN_OK)
    away_goals = away_icons.count(E_PEN_OK)
    if n_home <= 5 and n_away <= 5:
        # Entro i primi 5 tiri: decisa se il margine è incolmabile con i tiri
        # rimasti (copre anche 5-5 con punteggi diversi: zero tiri rimasti).
        home_left = 5 - n_home
        away_left = 5 - n_away
        return (home_goals > away_goals + away_left) or (away_goals > home_goals + home_left)
    # Oltre il 5°: sudden death, si decide solo a coppia di tiri completata
    # (il secondo tiratore batte sempre, quindi conteggi pari) con parità rotta.
    return n_home == n_away and home_goals != away_goals
