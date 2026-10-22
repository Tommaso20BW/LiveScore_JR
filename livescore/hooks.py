"""Punto di accesso unico ai pezzi del bot.

Il codice del bot e' diviso in moduli, ma il runtime dei kit (`kits/runtime.py`) e i test
hanno bisogno di *sostituire* alcune funzioni al volo (es. `bot.fetch_evento = proxy`).
`bot` fa da indirizzario: legge e scrive l'attributo direttamente nel modulo che lo possiede,
cosi' tutti gli altri moduli vedono subito la sostituzione.

Esempio::

    from livescore.hooks import bot
    bot.fetch_evento            # -> livescore.espn.client.fetch_evento
    with patch.object(bot, "send_telegram_get_id", return_value=42): ...

La tabella `OWNERS` elenca dove vive ogni nome: se sposti una funzione in un altro modulo,
aggiorna la riga (il test `tests/test_hooks.py` ti avvisa se dimentichi).
"""

from __future__ import annotations

import importlib

# nome -> modulo che lo definisce
OWNERS = {
    "BOT_JR_CHAT_ID": "livescore.settings",
    "BOT_TOKEN": "livescore.settings",
    "CANVA_DESIGN_ID": "livescore.settings",
    "CANVA_REFRESH_TOKEN": "livescore.canva.auth",
    "CHAT_ID": "livescore.settings",
    "CLIENT_ID": "livescore.settings",
    "CLIENT_SECRET": "livescore.settings",
    "ESPN_BASE": "livescore.constants",
    "ESPN_TZ": "livescore.constants",
    "EVENT_TYPE_MAP": "livescore.constants",
    "E_ASSIST": "livescore.constants",
    "E_BALL": "livescore.constants",
    "E_BOLT": "livescore.constants",
    "E_CANCEL": "livescore.constants",
    "E_CLOCK": "livescore.constants",
    "E_DOWN": "livescore.constants",
    "E_EXIT": "livescore.constants",
    "E_FLAG": "livescore.constants",
    "E_KICK": "livescore.constants",
    "E_MIC": "livescore.constants",
    "E_PEN_KO": "livescore.constants",
    "E_PEN_OK": "livescore.constants",
    "E_RED": "livescore.constants",
    "E_STATS": "livescore.constants",
    "E_SUB": "livescore.constants",
    "E_UP": "livescore.constants",
    "GH_PAT": "livescore.settings",
    "GIST_ID": "livescore.settings",
    "GITHUB_REPOSITORY": "livescore.settings",
    "GOAL_GRAPHICS_ENABLED": "livescore.settings",
    "ITALY_TZ": "livescore.constants",
    "JUVE_ID": "livescore.constants",
    "LEAGUE_MAP": "livescore.core.leagues",
    "LEAGUE_SLUGS": "livescore.core.leagues",
    "LIVE_LOG_HEARTBEAT_MINUTES": "livescore.settings",
    "MOMENTI_CONFIG": "livescore.constants",
    "MatchProgressLog": "livescore.core.log",
    "POLL_SECONDS": "livescore.settings",
    "SESSION": "livescore.core.http",
    "STATS_DELAY_SECONDS": "livescore.settings",
    "SUB_GROUP_SECONDS": "livescore.settings",
    "TEAM_ID": "livescore.settings",
    "TEAM_MAP": "livescore.core.team_names",
    "TELEGRAM_AUTO_DELETE_SECONDS": "livescore.settings",
    "_CANVA_ACCESS_EXPIRES_AT": "livescore.canva.auth",
    "_CANVA_ACCESS_TOKEN": "livescore.canva.auth",
    "_CT_ASSIST_RX": "livescore.constants",
    "_CT_GOAL_RX": "livescore.constants",
    "_CT_RED_RX": "livescore.constants",
    "_CT_YELLOW_RX": "livescore.constants",
    "_CUP_KEYWORDS": "livescore.core.leagues",
    "_ESPN_SHORT_NAMES": "livescore.core.text",
    "_FRIENDLY_KEYWORDS": "livescore.core.leagues",
    "_LEAGUES_JSON_PATH": "livescore.core.leagues",
    "_TEAMS_JSON_PATH": "livescore.core.team_names",
    "_estrai_stats_espn": "livescore.espn.stats",
    "_estrai_xg_mtchstatsgraph": "livescore.espn.stats",
    "_extract_team_id_from_commentary": "livescore.espn.parser",
    "_failpen_gia_inviato": "livescore.match.incidents",
    "_gist_headers": "livescore.state.gist",
    "_gist_retry_delay": "livescore.state.gist",
    "_is_league_slug": "livescore.core.leagues",
    "_load_leagues": "livescore.core.leagues",
    "_load_teams": "livescore.core.team_names",
    "_nome_portiere_registrato": "livescore.match.media",
    "_norm_name": "livescore.core.text",
    "_retry": "livescore.core.http",
    "_retry_graphic_on_text": "livescore.telegram.api",
    "_rigori_icone": "livescore.espn.parser",
    "_schedule_stats": "livescore.match.stats_job",
    "_send_telegram_event_photo_get_id": "livescore.telegram.api",
    "_shootout_deciso": "livescore.espn.parser",
    "_tg_post": "livescore.telegram.api",
    "avvia_ciclo_partita": "livescore.match.session",
    "build_hashtag": "livescore.core.team_names",
    "build_phase_graphic": "livescore.match.media",
    "build_score_str": "livescore.match.formatting",
    "delete_telegram_message": "livescore.telegram.api",
    "determina_kit": "livescore.kits.detect",
    "edit_telegram_goal_caption": "livescore.telegram.api",
    "edit_telegram_goal_photo": "livescore.telegram.api",
    "enqueue_response": "livescore.telegram.api",
    "esc": "livescore.core.text",
    "fetch_evento": "livescore.espn.client",
    "fmt_player": "livescore.core.text",
    "get_league_emoji": "livescore.core.leagues",
    "get_valid_token": "livescore.canva.auth",
    "goal_player_lines": "livescore.match.formatting",
    "goal_scoring_team_id": "livescore.match.formatting",
    "is_cup_competition": "livescore.core.leagues",
    "is_friendly_competition": "livescore.core.leagues",
    "leggi_stato_da_gist": "livescore.state.gist",
    "log_line": "livescore.core.log",
    "main": "livescore.match.session",
    "normalize_event_type": "livescore.espn.parser",
    "now_it": "livescore.core.text",
    "parse_events": "livescore.espn.parser",
    "parse_score": "livescore.espn.parser",
    "parse_status": "livescore.espn.parser",
    "phase_scorers_line": "livescore.match.formatting",
    "prepara_grafica_goal": "livescore.match.media",
    "prepara_grafica_parata_rigore": "livescore.match.media",
    "recupera_e_genera_stats_html": "livescore.match.stats_job",
    "recupera_xg_espn": "livescore.espn.stats",
    "replace_corrected_goal_message": "livescore.telegram.api",
    "resetta_gist": "livescore.state.gist",
    "rileva_kit_juve": "livescore.kits.detect",
    "salva_stato_su_gist": "livescore.state.gist",
    "send_phase_message": "livescore.match.media",
    "send_telegram": "livescore.telegram.api",
    "send_telegram_edit": "livescore.telegram.api",
    "send_telegram_get_id": "livescore.telegram.api",
    "send_telegram_goal_get_id": "livescore.telegram.api",
    "send_telegram_saved_get_id": "livescore.telegram.api",
    "send_telegram_stats_photo": "livescore.telegram.api",
    "send_telegram_with_photo": "livescore.telegram.api",
    "should_enqueue": "livescore.telegram.api",
    "stats_eligible": "livescore.match.stats_job",
    "translate_team": "livescore.core.team_names",
    "trova_partita_oggi": "livescore.espn.client",
    "trova_portiere_juve": "livescore.match.media",
    "update_github_secret": "livescore.canva.auth",
}

# nomi che sono essi stessi dei moduli
MODULES = {
    "fclogo_sync": "livescore.graphics.logos",
    "goal_graphics": "livescore.graphics.goal",
    "kit_analyzer": "livescore.kits.analyzer",
    "time": "time",
}


class _Bot:
    """Indirizzario dei pezzi del bot (vedi docstring del modulo)."""

    def __init__(self):
        object.__setattr__(self, "_previous", {})

    @staticmethod
    def _module(name: str):
        try:
            return importlib.import_module(OWNERS[name])
        except KeyError:
            raise AttributeError(f"'bot' non conosce '{name}'; aggiungilo a OWNERS in livescore/hooks.py") from None

    def __getattr__(self, name):
        if name in MODULES:
            return importlib.import_module(MODULES[name])
        return getattr(self._module(name), name)

    def __setattr__(self, name, value):
        module = self._module(name)
        self._previous.setdefault(name, []).append(getattr(module, name))
        setattr(module, name, value)

    def __delattr__(self, name):
        # chiamato da unittest.mock.patch alla fine: ripristina il valore precedente
        stack = self._previous.get(name)
        if not stack:
            raise AttributeError(name)
        setattr(self._module(name), name, stack.pop())


bot = _Bot()
