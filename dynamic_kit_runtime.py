"""
Dynamic Juventus kit runtime for LiveScore_JR.

Production integration goals:
- Read Juventus uniform.type from every ESPN summary already fetched by the bot.
  No extra ESPN polling is created.
- AUTO follows the latest valid ESPN home/away/third value.
- MANUAL keeps HOME/AWAY/THIRD until AUTO is selected again.
- HOME/AWAY/THIRD/AUTO buttons live on the Bot JR "PARTITA TROVATA" message.
- Already-published kit-dependent media are regenerated and edited in place.
- Canva phase graphics reuse the exact page-one snapshot used when published.
- Dynamic state and media metadata live inside the existing match Gist.
- At match end the inline keyboard is removed and local Canva snapshots are cleaned.

The module is installed by livescore_runner.py. It intentionally avoids changing
juve_bot_espn.py so the existing match/event logic stays untouched.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from canva_snapshot_store import GitHubSnapshotStore


VALID_KITS = ("home", "away", "third")
VALID_MODES = ("auto", "manual")
MAX_PROCESSED_CALLBACKS = 100


def _normalise_kit(value: Any) -> str | None:
    value = str(value or "").strip().lower()
    return value if value in VALID_KITS else None


def _display_kit(value: str | None) -> str:
    return {
        "home": "Home",
        "away": "Away",
        "third": "Third",
    }.get(value, "Non disponibile")


def _pixel_hash(png: bytes) -> str:
    """Hash visible pixels, so harmless PNG metadata changes do not force an edit."""
    with Image.open(io.BytesIO(png)) as image:
        rgba = image.convert("RGBA")
        payload = f"{rgba.width}x{rgba.height}:".encode() + rgba.tobytes()
    return hashlib.sha256(payload).hexdigest()


def _json_safe(value: Any) -> Any:
    """Convert Paths, tuples and nested structures to Gist-safe JSON values."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def extract_juventus_uniform(data: dict | None, juventus_id: str = "111") -> str | None:
    """Return the raw valid Juventus uniform.type from ESPN boxscore.teams."""
    if not isinstance(data, dict):
        return None

    teams = ((data.get("boxscore") or {}).get("teams") or [])
    for item in teams:
        if not isinstance(item, dict):
            continue
        team = item.get("team") or {}
        if str(team.get("id") or "") != str(juventus_id):
            continue
        kit = _normalise_kit((team.get("uniform") or {}).get("type"))
        if kit:
            return kit

    # Some ESPN payloads have no team.id inside boxscore.teams. Fall back to
    # homeAway by resolving the Juventus side from header competitors.
    competitions = ((data.get("header") or {}).get("competitions") or [])
    competitors = competitions[0].get("competitors", []) if competitions else []
    juventus_side = None
    for competitor in competitors:
        team = (competitor or {}).get("team") or {}
        if str(team.get("id") or "") == str(juventus_id):
            juventus_side = competitor.get("homeAway")
            break

    if juventus_side in ("home", "away"):
        for item in teams:
            if (item or {}).get("homeAway") != juventus_side:
                continue
            team = (item or {}).get("team") or {}
            kit = _normalise_kit((team.get("uniform") or {}).get("type"))
            if kit:
                return kit
    return None


def parse_callback_data(value: str) -> tuple[str | None, str | None]:
    parts = str(value or "").split(":")
    if len(parts) != 3 or parts[0] != "kit":
        return None, None
    return parts[1], parts[2]


def keyboard_for(event_id: str, kit_mode: str, active_kit: str) -> dict:
    selected = active_kit if kit_mode == "manual" else "auto"

    def button(choice: str) -> dict:
        label = choice.upper()
        if choice == selected:
            label = f"✅ {label}"
        return {
            "text": label,
            "callback_data": f"kit:{event_id}:{choice}",
        }

    return {
        "inline_keyboard": [[
            button("home"),
            button("away"),
            button("third"),
            button("auto"),
        ]]
    }


class DynamicKitRuntime:
    def __init__(self, bot):
        self.bot = bot
        self.installed = False

        self.current_event_id: str | None = None
        self.league_slug = ""
        self.league_name = ""
        self.home_id = ""
        self.away_id = ""
        self.home_name = ""
        self.away_name = ""
        self.enabled = False

        self.fallback_kit = "home"
        self.espn_kit: str | None = None
        self.active_kit = "home"
        self.kit_mode = "auto"
        self.manual_kit: str | None = None

        self.latest_summary: dict | None = None
        self.state_ref: dict | None = None
        self.volatile_media: dict[str, dict] = {}
        self.processed_callback_ids: list[str] = []
        self.update_offset: int | None = None

        self.recap_message_id: int | None = None
        self.recap_chat_id: str | None = None
        self.recap_text_factory: Callable[[], str] | None = None

        self.pending_render: dict[str, dict] = {}
        self.last_pending_label: str | None = None
        self._capturing_phase = False
        self._last_canva_snapshot: str | None = None
        self._suppress_capture = False

        self._originals: dict[str, Any] = {}
        self.canva_page_one = None
        self.stats_graphics = None
        self.portrait_graphics = None

        self.snapshot_store = GitHubSnapshotStore(
            token=(
                os.getenv("SNAPSHOT_GH_TOKEN")
                or getattr(bot, "GH_PAT", None)
            ),
            repository=getattr(bot, "GITHUB_REPOSITORY", None),
            session=getattr(bot, "SESSION", None),
            log=self._log,
        )

    # ------------------------------------------------------------------
    # Installation / compatibility hooks
    # ------------------------------------------------------------------
    def install(self) -> "DynamicKitRuntime":
        if self.installed:
            return self

        # Fix the already-existing ESPN-logo fallback NameError only for the
        # LiveScore process. The source file itself remains untouched.
        if not hasattr(self.bot.goal_graphics, "io"):
            self.bot.goal_graphics.io = io

        import canva_page_one
        import stats_graphics
        import portrait_graphics

        self.canva_page_one = canva_page_one
        self.stats_graphics = stats_graphics
        self.portrait_graphics = portrait_graphics

        self._originals = {
            "rileva_kit_juve": self.bot.rileva_kit_juve,
            "fetch_evento": self.bot.fetch_evento,
            "leggi_stato_da_gist": self.bot.leggi_stato_da_gist,
            "salva_stato_su_gist": self.bot.salva_stato_su_gist,
            "resetta_gist": self.bot.resetta_gist,
            "send_event_photo": self.bot._send_telegram_event_photo_get_id,
            "edit_goal_photo": self.bot.edit_telegram_goal_photo,
            "edit_goal_caption": self.bot.edit_telegram_goal_caption,
            "build_phase_graphic": self.bot.build_phase_graphic,
            "send_stats_photo": self.bot.send_telegram_stats_photo,
            "render_goal": self.bot.goal_graphics.render_goal_card,
            "render_saved": self.bot.goal_graphics.render_saved_card,
            "stats_build_html": stats_graphics.build_html,
            "canva_export": canva_page_one.export_page_one,
        }

        self.bot.rileva_kit_juve = self._rileva_kit_proxy
        self.bot.fetch_evento = self._fetch_evento_proxy
        self.bot.leggi_stato_da_gist = self._read_state_proxy
        self.bot.salva_stato_su_gist = self._save_state_proxy
        self.bot.resetta_gist = self._reset_state_proxy
        self.bot._send_telegram_event_photo_get_id = self._send_event_photo_proxy
        self.bot.edit_telegram_goal_photo = self._edit_goal_photo_proxy
        self.bot.edit_telegram_goal_caption = self._edit_goal_caption_proxy
        self.bot.build_phase_graphic = self._build_phase_graphic_proxy
        self.bot.send_telegram_stats_photo = self._send_stats_photo_proxy

        self.bot.goal_graphics.render_goal_card = self._render_goal_proxy
        self.bot.goal_graphics.render_saved_card = self._render_saved_proxy
        stats_graphics.build_html = self._stats_build_html_proxy
        canva_page_one.export_page_one = self._canva_export_proxy

        self.installed = True
        return self

    # ------------------------------------------------------------------
    # Match / state
    # ------------------------------------------------------------------
    def prepare_match(self, partita: dict, data: dict | None = None) -> None:
        """Bind the runtime to the discovered match before the recap is sent."""
        self.current_event_id = str(partita.get("event_id") or "")
        self.league_slug = str(partita.get("league_slug") or "")
        self.league_name = str(partita.get("league_name") or "")
        self.latest_summary = data if isinstance(data, dict) else None

        competition = {}
        competitions = ((data or {}).get("header") or {}).get("competitions") or []
        if competitions:
            competition.update(competitions[0] or {})
        else:
            competition.update(partita.get("competition") or {})
        competitors = competition.get("competitors") or partita.get("competitors") or []

        try:
            (
                self.home_id,
                self.away_id,
                self.home_name,
                self.away_name,
                _,
                _,
            ) = self.bot.parse_score(competitors)
        except Exception:
            self.home_id = self.away_id = ""
            self.home_name = self.away_name = ""

        juventus_match = str(self.bot.JUVE_ID) in (
            str(self.home_id),
            str(self.away_id),
        )
        friendly = self.bot.is_friendly_competition(
            self.league_slug,
            self.league_name,
        )
        self.enabled = bool(juventus_match and not friendly)

        fallback = self.bot.determina_kit(
            self.home_id,
            self.away_id,
            self.league_slug,
            self.league_name,
        )
        self.fallback_kit = _normalise_kit(fallback) or "home"

        raw_espn = extract_juventus_uniform(data, self.bot.JUVE_ID)
        self.espn_kit = raw_espn
        self.kit_mode = "auto"
        self.manual_kit = None
        self.active_kit = self.espn_kit or self.fallback_kit

        self.state_ref = None
        self.volatile_media = {}
        self.processed_callback_ids = []
        self.update_offset = None
        self.pending_render = {}
        self.last_pending_label = None
        self._last_canva_snapshot = None
        self.recap_message_id = None
        self.recap_chat_id = None
        self.recap_text_factory = None

        if self.enabled:
            self._drain_old_callbacks()

    def attach_recap(
        self,
        message_id: int | None,
        chat_id: str | int | None,
        text_factory: Callable[[], str] | None,
    ) -> None:
        if not message_id:
            return
        self.recap_message_id = int(message_id)
        self.recap_chat_id = str(chat_id) if chat_id is not None else None
        self.recap_text_factory = text_factory
        if self.state_ref is not None:
            self._sync_to_state(self.state_ref)
            self._persist_state()

    def mode_label_for(self, event_id: str | int | None) -> str | None:
        if not self.enabled or str(event_id or "") != str(self.current_event_id or ""):
            return None
        return self.kit_mode.upper()

    def keyboard_for_current(self) -> dict | None:
        if not self.enabled or not self.current_event_id:
            return None
        return keyboard_for(self.current_event_id, self.kit_mode, self.active_kit)

    def _state_matches_current(self, state: dict | None) -> bool:
        if not isinstance(state, dict) or not self.current_event_id:
            return False
        return str(state.get("event_id") or "") == str(self.current_event_id)

    def _ensure_state_defaults(self, state: dict) -> None:
        state.setdefault("kit_mode", "auto")
        state.setdefault("manual_kit", None)
        state.setdefault("espn_kit", self.espn_kit)
        state.setdefault("active_kit", self.active_kit)
        state.setdefault("kit_fallback", self.fallback_kit)
        state.setdefault("kit_media", {})
        state.setdefault("kit_update_offset", self.update_offset)
        state.setdefault("kit_processed_callbacks", [])
        state.setdefault("kit_recap_message_id", self.recap_message_id)

        if state.get("kit_mode") not in VALID_MODES:
            state["kit_mode"] = "auto"
        state["manual_kit"] = _normalise_kit(state.get("manual_kit"))
        state["espn_kit"] = _normalise_kit(state.get("espn_kit"))
        state["kit_fallback"] = (
            _normalise_kit(state.get("kit_fallback"))
            or self.fallback_kit
        )

        if not isinstance(state.get("kit_media"), dict):
            state["kit_media"] = {}
        if not isinstance(state.get("kit_processed_callbacks"), list):
            state["kit_processed_callbacks"] = []

        if state["kit_mode"] == "manual" and state["manual_kit"]:
            state["active_kit"] = state["manual_kit"]
        else:
            state["kit_mode"] = "auto"
            state["manual_kit"] = None
            state["active_kit"] = (
                state["espn_kit"] or state["kit_fallback"]
            )

    def _hydrate_from_state(self, state: dict) -> None:
        self._ensure_state_defaults(state)

        current_summary_kit = extract_juventus_uniform(
            self.latest_summary,
            self.bot.JUVE_ID,
        )
        persisted_espn = _normalise_kit(state.get("espn_kit"))
        self.espn_kit = current_summary_kit or persisted_espn or self.espn_kit

        self.kit_mode = (
            state.get("kit_mode")
            if state.get("kit_mode") in VALID_MODES
            else "auto"
        )
        self.manual_kit = _normalise_kit(state.get("manual_kit"))
        self.fallback_kit = (
            _normalise_kit(state.get("kit_fallback"))
            or self.fallback_kit
        )

        if self.kit_mode == "manual" and self.manual_kit:
            self.active_kit = self.manual_kit
        else:
            self.kit_mode = "auto"
            self.manual_kit = None
            self.active_kit = self.espn_kit or self.fallback_kit

        persisted_media = state.get("kit_media")
        if isinstance(persisted_media, dict):
            persisted_media.update(self.volatile_media)
            self.volatile_media = persisted_media

        persisted_callbacks = state.get("kit_processed_callbacks") or []
        merged_callbacks = list(dict.fromkeys(
            [*persisted_callbacks, *self.processed_callback_ids]
        ))
        self.processed_callback_ids = merged_callbacks[-MAX_PROCESSED_CALLBACKS:]

        persisted_offset = state.get("kit_update_offset")
        if isinstance(persisted_offset, int):
            if self.update_offset is None:
                self.update_offset = persisted_offset
            else:
                self.update_offset = max(self.update_offset, persisted_offset)

        if not self.recap_message_id:
            persisted_recap = state.get("kit_recap_message_id")
            if persisted_recap:
                try:
                    self.recap_message_id = int(persisted_recap)
                except (TypeError, ValueError):
                    pass

        self.state_ref = state
        self._sync_to_state(state)
        self._edit_recap()

    def _sync_to_state(self, state: dict) -> None:
        if not self._state_matches_current(state):
            return
        self._ensure_state_defaults(state)
        state["kit_mode"] = self.kit_mode
        state["manual_kit"] = self.manual_kit
        state["espn_kit"] = self.espn_kit
        state["active_kit"] = self.active_kit
        state["kit_fallback"] = self.fallback_kit
        state["kit_media"] = self.volatile_media
        state["kit_update_offset"] = self.update_offset
        state["kit_processed_callbacks"] = self.processed_callback_ids[
            -MAX_PROCESSED_CALLBACKS:
        ]
        state["kit_recap_message_id"] = self.recap_message_id

    def _persist_state(self) -> None:
        if not self._state_matches_current(self.state_ref):
            return
        try:
            self._sync_to_state(self.state_ref)
            self._originals["salva_stato_su_gist"](self.state_ref)
        except Exception as exc:
            self._log("WARN", "STATE", f"Kit dinamico: salvataggio Gist fallito: {exc}")

    def _read_state_proxy(self):
        result = self._originals["leggi_stato_da_gist"]()
        try:
            ok, state = result
        except Exception:
            return result
        if ok and self._state_matches_current(state):
            self._hydrate_from_state(state)
        return result

    def _save_state_proxy(self, state: dict):
        if self._state_matches_current(state):
            self.state_ref = state
            if self.volatile_media:
                existing = state.get("kit_media")
                if isinstance(existing, dict):
                    existing.update(self.volatile_media)
                    self.volatile_media = existing
            self._sync_to_state(state)
        return self._originals["salva_stato_su_gist"](state)

    def _reset_state_proxy(self):
        # Current juve_bot_espn calls resetta_gist only at final shutdown.
        # Remove buttons before the state disappears.
        self.finish_match()
        return self._originals["resetta_gist"]()

    # ------------------------------------------------------------------
    # ESPN / active kit
    # ------------------------------------------------------------------
    def _rileva_kit_proxy(
        self,
        data_espn: dict,
        home_id: str,
        away_id: str,
        home_name: str,
        away_name: str,
        league_slug: str = "",
        league_name: str = "",
    ) -> str:
        if (
            self.enabled
            and str(self.bot.JUVE_ID) in (str(home_id), str(away_id))
            and str(league_slug or "") == str(self.league_slug or "")
        ):
            return self.active_kit
        return self._originals["rileva_kit_juve"](
            data_espn,
            home_id,
            away_id,
            home_name,
            away_name,
            league_slug,
            league_name,
        )

    def _fetch_evento_proxy(self, event_id, league_slug):
        data = self._originals["fetch_evento"](event_id, league_slug)
        if (
            self.enabled
            and str(event_id or "") == str(self.current_event_id or "")
            and isinstance(data, dict)
        ):
            self.latest_summary = data
            self.observe_summary(data)
            self.poll_callbacks()
        return data

    def observe_summary(self, data: dict) -> None:
        """Called for every normal ESPN summary response of the active match."""
        detected = extract_juventus_uniform(data, self.bot.JUVE_ID)
        if not detected:
            # Keep the last valid ESPN value. AUTO therefore uses:
            # last valid ESPN uniform -> fallback if ESPN has never provided one.
            return

        old_espn = self.espn_kit
        old_active = self.active_kit
        self.espn_kit = detected

        if old_espn != self.espn_kit:
            self._log(
                "INFO",
                "KIT",
                f"ESPN uniform: {_display_kit(old_espn)} -> {_display_kit(self.espn_kit)}",
            )

        if self.kit_mode == "auto":
            self.active_kit = self.espn_kit or self.fallback_kit

        if old_espn != self.espn_kit:
            self._persist_state()
            self._edit_recap()

        if old_active != self.active_kit:
            self._log(
                "INFO",
                "KIT",
                f"ACTIVE KIT: {old_active} -> {self.active_kit} | mode=AUTO",
            )
            self.refresh_all_media()
            self._persist_state()
            self._edit_recap()

    # ------------------------------------------------------------------
    # Telegram callbacks
    # ------------------------------------------------------------------
    def _drain_old_callbacks(self) -> None:
        if not self.bot.BOT_TOKEN:
            return
        try:
            response = self.bot._tg_post(
                "getUpdates",
                data={
                    "timeout": "0",
                    "allowed_updates": json.dumps(["callback_query"]),
                },
                timeout=5,
            )
            if response is None or response.status_code != 200:
                return
            payload = response.json()
            updates = payload.get("result") or []
            if updates:
                self.update_offset = max(
                    int(update.get("update_id", 0))
                    for update in updates
                ) + 1
        except Exception as exc:
            self._log("DEBUG", "KIT", f"Drain callback saltato: {exc}")

    def poll_callbacks(self) -> None:
        if not self.enabled or not self.bot.BOT_TOKEN:
            return

        data = {
            "timeout": "0",
            "allowed_updates": json.dumps(["callback_query"]),
        }
        if self.update_offset is not None:
            data["offset"] = str(self.update_offset)

        try:
            response = self.bot._tg_post(
                "getUpdates",
                data=data,
                timeout=5,
            )
            if response is None or response.status_code != 200:
                return
            updates = response.json().get("result") or []
        except Exception as exc:
            self._log("DEBUG", "KIT", f"getUpdates fallita: {exc}")
            return

        offset_changed = False
        for update in updates:
            try:
                update_id = int(update.get("update_id", 0))
            except (TypeError, ValueError):
                update_id = 0
            if self.update_offset is None or update_id >= self.update_offset:
                self.update_offset = update_id + 1
                offset_changed = True

            callback = update.get("callback_query") or {}
            callback_id = str(callback.get("id") or "")
            callback_data = str(callback.get("data") or "")
            message = callback.get("message") or {}
            chat_id = str(((message.get("chat") or {}).get("id")) or "")

            event_id, choice = parse_callback_data(callback_data)
            if not callback_id:
                continue

            if (
                self.recap_chat_id
                and chat_id
                and chat_id != str(self.recap_chat_id)
            ):
                self._answer_callback(callback_id, "Messaggio non valido")
                continue

            if event_id != str(self.current_event_id or ""):
                self._answer_callback(callback_id, "Evento non attivo")
                continue

            if callback_id in self.processed_callback_ids:
                self._answer_callback(callback_id, "Già applicato")
                continue

            if choice not in (*VALID_KITS, "auto"):
                self._answer_callback(callback_id, "Scelta non valida")
                continue

            self.processed_callback_ids.append(callback_id)
            self.processed_callback_ids = self.processed_callback_ids[
                -MAX_PROCESSED_CALLBACKS:
            ]

            old_active = self.active_kit
            if choice == "auto":
                self.kit_mode = "auto"
                self.manual_kit = None
                self.active_kit = self.espn_kit or self.fallback_kit
                answer = f"AUTO · {_display_kit(self.active_kit)}"
            else:
                self.kit_mode = "manual"
                self.manual_kit = choice
                self.active_kit = choice
                answer = f"MANUALE · {_display_kit(self.active_kit)}"

            self._persist_state()
            self._answer_callback(callback_id, answer)

            if old_active != self.active_kit:
                self._log(
                    "INFO",
                    "KIT",
                    f"Override Bot JR: {old_active} -> {self.active_kit} | "
                    f"mode={self.kit_mode.upper()}",
                )
                self.refresh_all_media()
                self._persist_state()

            self._edit_recap()

        if offset_changed:
            self._persist_state()

    def _answer_callback(self, callback_id: str, text: str) -> None:
        try:
            response = self.bot._tg_post(
                "answerCallbackQuery",
                data={
                    "callback_query_id": callback_id,
                    "text": text[:180],
                    "show_alert": "false",
                },
                timeout=10,
            )
            if response is not None:
                response.raise_for_status()
        except Exception as exc:
            self._log("DEBUG", "KIT", f"answerCallbackQuery fallita: {exc}")

    def _edit_recap(self) -> None:
        if (
            not self.enabled
            or not self.recap_message_id
            or not self.recap_chat_id
            or not self.recap_text_factory
        ):
            return
        try:
            text = self.recap_text_factory()
            response = self.bot._tg_post(
                "editMessageText",
                data={
                    "chat_id": self.recap_chat_id,
                    "message_id": self.recap_message_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(
                        self.keyboard_for_current(),
                        ensure_ascii=False,
                    ),
                },
                timeout=15,
            )
            if response is not None:
                response.raise_for_status()
        except Exception as exc:
            # "message is not modified" is harmless and can occur if ESPN repeats
            # an already-visible state.
            self._log("DEBUG", "KIT", f"Aggiornamento recap Bot JR saltato: {exc}")

    def remove_recap_buttons(self) -> None:
        if not self.recap_message_id or not self.recap_chat_id:
            return
        try:
            response = self.bot._tg_post(
                "editMessageReplyMarkup",
                data={
                    "chat_id": self.recap_chat_id,
                    "message_id": self.recap_message_id,
                    "reply_markup": json.dumps({"inline_keyboard": []}),
                },
                timeout=15,
            )
            if response is not None:
                response.raise_for_status()
            self._log("OK", "KIT", "Pulsanti kit rimossi dal recap Bot JR")
        except Exception as exc:
            self._log("WARN", "KIT", f"Rimozione pulsanti Bot JR fallita: {exc}")

    # ------------------------------------------------------------------
    # Render capture / media registry
    # ------------------------------------------------------------------
    def _render_goal_proxy(self, *args, **kwargs):
        rendered = self._originals["render_goal"](*args, **kwargs)
        if self.enabled and not self._suppress_capture and rendered is not None:
            context = self._goal_context(kwargs, rendered, "goal")
            self._set_pending("goal", context, rendered.png)
        return rendered

    def _render_saved_proxy(self, *args, **kwargs):
        rendered = self._originals["render_saved"](*args, **kwargs)
        if self.enabled and not self._suppress_capture and rendered is not None:
            context = self._goal_context(kwargs, rendered, "saved")
            self._set_pending("saved", context, rendered.png)
        return rendered

    def _goal_context(self, kwargs: dict, rendered, kind: str) -> dict:
        allowed = {
            "scorer_name",
            "goalkeeper_name",
            "minute",
            "home_name",
            "away_name",
            "home_goals",
            "away_goals",
            "kit",
            "goal_type",
            "home_id",
            "away_id",
            "pose",
            "event_key",
            "competition",
        }
        render = {
            key: _json_safe(value)
            for key, value in kwargs.items()
            if key in allowed
        }

        # The renderer may choose a deterministic pose. Persist the chosen pose
        # so a later kit edit reproduces the same composition.
        pose = getattr(rendered, "pose", None)
        if pose:
            render["pose"] = pose
        render["kit"] = self.active_kit

        return {
            "type": kind,
            "render": render,
            "event_key": str(render.get("event_key") or ""),
            "canva_snapshot": None,
        }

    def _build_phase_graphic_proxy(self, *args, **kwargs):
        kind = str(kwargs.get("kind") or "")
        self._capturing_phase = True
        self._last_canva_snapshot = None
        try:
            png = self._originals["build_phase_graphic"](*args, **kwargs)
        finally:
            self._capturing_phase = False

        if self.enabled and not self._suppress_capture and png:
            allowed = {
                "kind",
                "home_id",
                "away_id",
                "home_name",
                "away_name",
                "league_slug",
                "league_name",
                "home_goals",
                "away_goals",
                "shootout",
            }
            render = {
                key: _json_safe(value)
                for key, value in kwargs.items()
                if key in allowed
            }
            local_snapshot = (
                self._last_canva_snapshot
                if kind != "kick"
                else None
            )
            remote_snapshot = None
            if kind != "kick":
                if not local_snapshot:
                    self._log(
                        "ERROR",
                        "CANVA",
                        f"Snapshot locale assente per {kind}; foto non pubblicata",
                    )
                    return None
                try:
                    remote_snapshot = self.snapshot_store.persist_snapshot(
                        event_id=str(self.current_event_id or "unknown"),
                        kind=kind,
                        snapshot_dir=Path(local_snapshot),
                    )
                except Exception as exc:
                    # Do not publish a phase photo that could become
                    # unrecoverable after a runner restart. Returning None
                    # activates the bot's existing text fallback/retry path.
                    self._log(
                        "ERROR",
                        "CANVA",
                        f"Persistenza snapshot remoto {kind} fallita: {exc}; "
                        "foto non pubblicata",
                    )
                    return None

            context = {
                "type": kind,
                "render": render,
                "event_key": "",
                "canva_snapshot": local_snapshot,
                "canva_snapshot_remote": remote_snapshot,
            }
            self._set_pending(kind, context, png)
        return png

    def _canva_export_proxy(self, *args, **kwargs):
        result = self._originals["canva_export"](*args, **kwargs)
        if self._capturing_phase and result is not None:
            path = Path(result)
            # export_page_one already stores a content-addressed folder containing
            # source.pdf, background.png, player.png and manifest.json. That exact
            # folder is the immutable snapshot for this published phase card.
            self._last_canva_snapshot = str(path)
            self._log(
                "DEBUG",
                "CANVA",
                f"Snapshot congelato: {path}",
            )
        return result

    def _stats_build_html_proxy(self, *args, **kwargs):
        html = self._originals["stats_build_html"](*args, **kwargs)
        if self.enabled and not self._suppress_capture:
            render = {
                key: _json_safe(value)
                for key, value in kwargs.items()
                if key in {
                    "rows",
                    "kit",
                    "competition",
                    "league_name",
                    "momento",
                    "home_id",
                    "away_id",
                    "home_name",
                    "away_name",
                }
            }
            render["kit"] = self.active_kit
            self.pending_render["stats"] = {
                "type": "stats",
                "render": render,
                "event_key": "",
                "canva_snapshot": None,
            }
            self.last_pending_label = "stats"
        return html

    def _set_pending(self, label: str, context: dict, png: bytes) -> None:
        context = copy.deepcopy(context)
        context["visual_hash"] = _pixel_hash(png)
        context["kit"] = self.active_kit
        self.pending_render[str(label).lower()] = context
        self.last_pending_label = str(label).lower()

    def _send_event_photo_proxy(
        self,
        text: str,
        photo_bytes: bytes | None,
        *,
        filename: str,
        label: str,
        retry_factory=None,
    ):
        result = self._originals["send_event_photo"](
            text,
            photo_bytes,
            filename=filename,
            label=label,
            retry_factory=retry_factory,
        )
        try:
            message_id, sent_as_photo = result
        except Exception:
            return result

        key = str(label or "").lower()
        if message_id and sent_as_photo:
            context = self.pending_render.get(key)
            if context is None and self.last_pending_label:
                context = self.pending_render.get(self.last_pending_label)
            if context is not None:
                self._register_media(
                    message_id=int(message_id),
                    caption=text,
                    context=context,
                    chat_id=self.bot.CHAT_ID,
                )
        self.pending_render.pop(key, None)
        return result

    def _edit_goal_photo_proxy(
        self,
        message_id: int,
        text: str,
        photo_bytes: bytes,
    ) -> bool:
        ok = self._originals["edit_goal_photo"](
            message_id,
            text,
            photo_bytes,
        )
        if ok and self.enabled:
            context = None
            if self.last_pending_label:
                context = self.pending_render.get(self.last_pending_label)
            if context is not None:
                # Use the actual bytes passed to Telegram, not a previous attempt.
                context = copy.deepcopy(context)
                context["visual_hash"] = _pixel_hash(photo_bytes)
                context["kit"] = self.active_kit
                self._register_media(
                    message_id=int(message_id),
                    caption=text,
                    context=context,
                    chat_id=self.bot.CHAT_ID,
                )
            else:
                record = self.volatile_media.get(str(message_id))
                if isinstance(record, dict):
                    record["caption"] = text
                    record["visual_hash"] = _pixel_hash(photo_bytes)
                    record["kit"] = self.active_kit
                    self._persist_state()
        return ok

    def _edit_goal_caption_proxy(self, message_id: int, text: str) -> bool:
        ok = self._originals["edit_goal_caption"](message_id, text)
        if ok:
            record = self.volatile_media.get(str(message_id))
            if isinstance(record, dict):
                record["caption"] = text
                self._persist_state()
        return ok

    def _send_stats_photo_proxy(
        self,
        png_path: str,
        momento: str,
        hashtag: str,
        min_long_side: int = 2000,
    ) -> bool:
        """
        Same production behavior as juve_bot_espn.send_telegram_stats_photo,
        plus message_id capture for later editMessageMedia.
        """
        if not png_path:
            self._log(
                "WARN",
                "STATS",
                f"{momento} | immagine non generata; invio saltato",
            )
            return False

        caption = (
            f"{self.bot.MOMENTI_CONFIG[momento]['titolo']}\n\n{hashtag}"
        )
        try:
            path = Path(png_path)
            png_bytes = path.read_bytes()
            with path.open("rb") as handle:
                response = self.bot._tg_post(
                    "sendPhoto",
                    data={
                        "chat_id": self.bot.CHAT_ID,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={
                        "photo": (
                            "stats.png",
                            handle,
                            "image/png",
                        )
                    },
                    timeout=25,
                )

            if response is None:
                return False
            response.raise_for_status()
            result = response.json().get("result", {})
            message_id = result.get("message_id")

            if min_long_side:
                photo_sizes = result.get("photo", [])
                largest = max(
                    photo_sizes,
                    key=lambda item: (
                        item.get("width", 0) * item.get("height", 0)
                    ),
                    default={},
                )
                sent_w = largest.get("width", 0)
                sent_h = largest.get("height", 0)
                if max(sent_w, sent_h) >= min_long_side:
                    self._log(
                        "OK",
                        "STATS",
                        f"Variante Telegram HD | {sent_w}x{sent_h}",
                    )
                else:
                    self._log(
                        "WARN",
                        "STATS",
                        f"Telegram ha restituito solo {sent_w}x{sent_h}",
                    )

            context = self.pending_render.get("stats")
            if message_id and context is not None:
                context = copy.deepcopy(context)
                context["visual_hash"] = _pixel_hash(png_bytes)
                context["kit"] = self.active_kit
                self._register_media(
                    message_id=int(message_id),
                    caption=caption,
                    context=context,
                    chat_id=self.bot.CHAT_ID,
                )
            self.pending_render.pop("stats", None)
            return True

        except Exception as exc:
            self._log(
                "ERROR",
                "STATS",
                f"{momento} | invio foto Telegram fallito: {exc}",
            )
            return False

    def _register_media(
        self,
        *,
        message_id: int,
        caption: str,
        context: dict,
        chat_id: str | int | None,
    ) -> None:
        record = {
            "message_id": int(message_id),
            "chat_id": str(chat_id or self.bot.CHAT_ID or ""),
            "type": str(context.get("type") or ""),
            "caption": caption,
            "kit": self.active_kit,
            "visual_hash": context.get("visual_hash"),
            "event_key": str(context.get("event_key") or ""),
            "render": _json_safe(context.get("render") or {}),
            "canva_snapshot": context.get("canva_snapshot"),
            "canva_snapshot_remote": _json_safe(
                context.get("canva_snapshot_remote")
            ),
            "last_edit_error": None,
        }
        self.volatile_media[str(message_id)] = record
        self._persist_state()
        self._log(
            "DEBUG",
            "KIT",
            f"Media registrato | type={record['type']} | "
            f"message_id={message_id} | kit={self.active_kit}",
        )

    # ------------------------------------------------------------------
    # Regeneration / edit in place
    # ------------------------------------------------------------------
    def refresh_all_media(self) -> tuple[int, int, int]:
        if not self.enabled or not self.volatile_media:
            return 0, 0, 0

        edited = 0
        identical = 0
        failed = 0

        self._suppress_capture = True
        try:
            for message_key, record in list(self.volatile_media.items()):
                if not isinstance(record, dict):
                    continue
                if record.get("kit") == self.active_kit:
                    continue

                try:
                    png = self._render_record(record, self.active_kit)
                    new_hash = _pixel_hash(png)

                    if new_hash == record.get("visual_hash"):
                        record["kit"] = self.active_kit
                        record["last_edit_error"] = None
                        identical += 1
                        self._log(
                            "DEBUG",
                            "KIT",
                            f"Nessun cambio visivo | {record.get('type')} | "
                            f"message_id={record.get('message_id')}",
                        )
                        continue

                    if self._edit_media_record(record, png):
                        record["kit"] = self.active_kit
                        record["visual_hash"] = new_hash
                        record["last_edit_error"] = None
                        edited += 1
                    else:
                        record["last_edit_error"] = (
                            f"editMessageMedia fallito verso {self.active_kit}"
                        )
                        failed += 1

                except Exception as exc:
                    record["last_edit_error"] = (
                        f"{type(exc).__name__}: {exc}"
                    )
                    failed += 1
                    self._log(
                        "WARN",
                        "KIT",
                        f"Rigenerazione {record.get('type')} fallita | "
                        f"message_id={record.get('message_id')} | {exc}",
                    )
        finally:
            self._suppress_capture = False

        self._persist_state()
        self._log(
            "INFO",
            "KIT",
            f"Propagazione kit {self.active_kit}: "
            f"edit={edited}, invariati={identical}, errori={failed}",
        )
        return edited, identical, failed

    def _render_record(self, record: dict, kit: str) -> bytes:
        kind = str(record.get("type") or "")
        render = copy.deepcopy(record.get("render") or {})

        if kind == "goal":
            render["kit"] = kit
            return self._originals["render_goal"](**render).png

        if kind == "saved":
            render["kit"] = kit
            return self._originals["render_saved"](**render).png

        if kind in ("kick", "half", "full", "end_of_90"):
            snapshot = record.get("canva_snapshot")
            layers = None
            if kind != "kick":
                layers = Path(snapshot) if snapshot else None
                required_names = (
                    "source.pdf",
                    "background.png",
                    "player.png",
                    "manifest.json",
                )

                def snapshot_missing(path):
                    return (
                        path is None
                        or any(
                            not (path / name).is_file()
                            for name in required_names
                        )
                    )

                if snapshot_missing(layers):
                    remote = record.get("canva_snapshot_remote")
                    if not isinstance(remote, dict):
                        raise FileNotFoundError(
                            f"Snapshot Canva locale e remoto assenti per {kind}"
                        )
                    layers = self.snapshot_store.restore_snapshot(
                        remote,
                        destination_root=Path("canva_page1_cache"),
                    )
                    record["canva_snapshot"] = str(layers)
                    self._persist_state()

                missing = [
                    str(layers / name)
                    for name in required_names
                    if not (layers / name).is_file()
                ]
                if missing:
                    raise FileNotFoundError(
                        "Snapshot Canva incompleto dopo ripristino: "
                        + ", ".join(missing)
                    )

            return self.portrait_graphics.phase(
                kind=kind,
                home_name=render.get("home_name", self.home_name),
                away_name=render.get("away_name", self.away_name),
                home_id=render.get("home_id", self.home_id),
                away_id=render.get("away_id", self.away_id),
                home_goals=int(render.get("home_goals", 0) or 0),
                away_goals=int(render.get("away_goals", 0) or 0),
                kit=kit,
                competition=render.get(
                    "league_slug",
                    self.league_slug,
                ),
                layers=layers,
                shootout=render.get("shootout"),
            )

        if kind == "stats":
            render["kit"] = kit
            html = self._originals["stats_build_html"](**render)
            path = self.stats_graphics.render(html, hd_output=True)
            return Path(path).read_bytes()

        raise ValueError(f"Tipo media non supportato: {kind}")

    def _edit_media_record(self, record: dict, png: bytes) -> bool:
        media = json.dumps({
            "type": "photo",
            "media": "attach://photo",
            "caption": record.get("caption") or "",
            "parse_mode": "HTML",
        })
        try:
            response = self.bot._tg_post(
                "editMessageMedia",
                data={
                    "chat_id": record.get("chat_id") or self.bot.CHAT_ID,
                    "message_id": int(record["message_id"]),
                    "media": media,
                },
                files={
                    "photo": (
                        "kit-refresh.png",
                        png,
                        "image/png",
                    )
                },
                timeout=30,
            )
            if response is None:
                return False
            response.raise_for_status()
            self._log(
                "OK",
                "KIT",
                f"MEDIA EDIT | type={record.get('type')} | "
                f"message_id={record.get('message_id')} | "
                f"kit={self.active_kit}",
            )
            return True
        except Exception as exc:
            self._log(
                "WARN",
                "KIT",
                f"editMessageMedia fallita | "
                f"message_id={record.get('message_id')} | {exc}",
            )
            return False

    # ------------------------------------------------------------------
    # End of match / cleanup
    # ------------------------------------------------------------------
    def finish_match(self) -> None:
        self.remove_recap_buttons()
        self._cleanup_remote_canva_snapshots()
        self._cleanup_canva_snapshots()

    def _cleanup_remote_canva_snapshots(self) -> None:
        if not self.current_event_id:
            return
        try:
            self.snapshot_store.cleanup_event(
                str(self.current_event_id)
            )
        except Exception as exc:
            # Never block final shutdown/Gist reset because remote cleanup
            # failed. Leftover files are harmless and can be removed later.
            self._log(
                "WARN",
                "CANVA",
                f"Cleanup snapshot remoti fallito: {exc}",
            )

    def _cleanup_canva_snapshots(self) -> None:
        # Production build_phase_graphic uses this cache. At FT all phase/media
        # retries are finished, so the complete temporary snapshot cache can go.
        cache = Path("canva_page1_cache")
        try:
            if cache.exists():
                shutil.rmtree(cache)
                self._log(
                    "DEBUG",
                    "CANVA",
                    "Snapshot Canva temporanei eliminati a fine partita",
                )
        except Exception as exc:
            self._log(
                "WARN",
                "CANVA",
                f"Pulizia snapshot Canva fallita: {exc}",
            )

    # ------------------------------------------------------------------
    def _log(self, level: str, area: str, message: str) -> None:
        try:
            self.bot.log_line(level, area, message)
        except Exception:
            print(f"[{level}] {area}: {message}", flush=True)
