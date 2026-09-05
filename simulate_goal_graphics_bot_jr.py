"""Replay controllato di eventi ESPN per collaudare GOAL/SAVED su Bot JR."""

from __future__ import annotations

import argparse
import sys
import time

import juve_bot_espn as bot


HOME_ID = "111"
AWAY_ID = "110"
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"


def espn_payload(kit: str) -> dict:
    """Payload minimo con la stessa struttura uniform usata dal live ESPN."""
    return {
        "header": {
            "competitions": [{
                "competitors": [
                    {
                        "homeAway": "home",
                        "team": {
                            "id": HOME_ID,
                            "displayName": HOME_NAME,
                            "color": "000000",
                        },
                    },
                    {
                        "homeAway": "away",
                        "team": {
                            "id": AWAY_ID,
                            "displayName": AWAY_NAME,
                            "color": "0068A8",
                        },
                    },
                ]
            }]
        },
        "boxscore": {
            "teams": [
                {
                    "homeAway": "home",
                    "team": {
                        "id": HOME_ID,
                        "uniform": {"type": kit, "color": "FFFFFF"},
                    },
                },
                {
                    "homeAway": "away",
                    "team": {
                        "id": AWAY_ID,
                        "uniform": {"type": "away", "color": "0068A8"},
                    },
                },
            ]
        },
    }


def goal_caption(
    case: str,
    player_name: str,
    assist_name: str,
    goal_type: str,
    minute: str,
    home_goals: int,
    away_goals: int,
    scoring_team_id: str,
) -> str:
    scorer_line, assist_line = bot.goal_player_lines(
        player_name, assist_name, goal_type, scoring_team_id
    )
    if scoring_team_id == HOME_ID:
        score = f"<b>{HOME_NAME} {home_goals}</b>-{away_goals} {AWAY_NAME}"
    else:
        score = f"{HOME_NAME} {home_goals}-<b>{away_goals} {AWAY_NAME}</b>"
    return (
        f"<b>🧪 TEST ESPN — {case}</b>\n"
        f"<b>GOAL · {minute}' {bot.E_MIC}</b>\n\n"
        f"{score}\n{scorer_line}{assist_line}\n⚽️ #JuventusInter"
    )


def render_goal(
    *,
    player_name: str,
    goal_type: str,
    minute: str,
    home_goals: int,
    away_goals: int,
    scoring_team_id: str,
    kit: str,
    event_key: str,
):
    return bot.prepara_grafica_goal(
        data_espn=espn_payload(kit),
        scorer_name=player_name,
        goal_type=goal_type,
        scoring_team_id=scoring_team_id,
        minute=minute,
        home_name=HOME_NAME,
        away_name=AWAY_NAME,
        home_id=HOME_ID,
        away_id=AWAY_ID,
        home_goals=home_goals,
        away_goals=away_goals,
        league_slug="ita.1",
        league_name="Serie A",
        event_key=event_key,
    )


def send_goal_case(
    *,
    send: bool,
    case: str,
    player_name: str,
    assist_name: str = "",
    goal_type: str = "goal",
    minute: str,
    home_goals: int,
    away_goals: int,
    scoring_team_id: str = HOME_ID,
    kit: str = "home",
    expect_photo: bool,
) -> tuple[int, bool, object | None, str]:
    key = "simulation|" + case.lower().replace(" ", "-")
    rendered = render_goal(
        player_name=player_name,
        goal_type=goal_type,
        minute=minute,
        home_goals=home_goals,
        away_goals=away_goals,
        scoring_team_id=scoring_team_id,
        kit=kit,
        event_key=key,
    )
    if bool(rendered) != expect_photo:
        raise RuntimeError(
            f"{case}: card attesa={expect_photo}, ottenuta={bool(rendered)}"
        )
    text = goal_caption(
        case,
        player_name,
        assist_name,
        goal_type,
        minute,
        home_goals,
        away_goals,
        scoring_team_id,
    )
    if not send:
        print(f"OK {case}: {'foto' if rendered else 'solo testo'}")
        return 1000, bool(rendered), rendered, text
    message_id, sent_as_photo = bot.send_telegram_goal_get_id(
        text, rendered.png if rendered else None
    )
    if not message_id or sent_as_photo != expect_photo:
        raise RuntimeError(
            f"{case}: invio Telegram non riuscito o tipo media inatteso"
        )
    time.sleep(1)
    return message_id, sent_as_photo, rendered, text


def send_text(send: bool, text: str) -> None:
    if not send:
        print("OK messaggio testuale")
        return
    if not bot.send_telegram_get_id(text):
        raise RuntimeError("Invio messaggio testuale Bot JR non riuscito")
    time.sleep(1)


def run(send: bool) -> None:
    bot.GOAL_GRAPHICS_ENABLED = True
    if send:
        if not bot.BOT_TOKEN or not bot.BOT_JR_CHAT_ID:
            raise RuntimeError("TELEGRAM_TOKEN/TELEGRAM_TO_BOT assenti")
        # Blocco di sicurezza: il simulatore non puo mai scrivere nel canale principale.
        bot.CHAT_ID = bot.BOT_JR_CHAT_ID
        send_text(
            True,
            "<b>🧪 INIZIO TEST GRAFICHE — REPLAY ESPN SIMULATO</b>\n\n"
            "Tutti gli eventi seguenti sono artificiali e destinati soltanto a Bot JR.",
        )

    send_goal_case(
        send=send,
        case="GOL NORMALE — HOME",
        player_name="Kenan Yildiz",
        assist_name="Manuel Locatelli",
        minute="12",
        home_goals=1,
        away_goals=0,
        kit="home",
        expect_photo=True,
    )
    send_goal_case(
        send=send,
        case="GOL SU RIGORE — AWAY",
        player_name="Nick Woltemade",
        goal_type="penalty goal",
        minute="31",
        home_goals=2,
        away_goals=0,
        kit="away",
        expect_photo=True,
    )
    send_goal_case(
        send=send,
        case="AUTOGOL A FAVORE JUVENTUS",
        player_name="Alessandro Bastoni",
        assist_name="Nicolò Barella",
        goal_type="own goal",
        minute="48",
        home_goals=3,
        away_goals=0,
        expect_photo=True,
    )
    send_goal_case(
        send=send,
        case="MARCATORE SENZA ASSET",
        player_name="Nuovo Giocatore ESPN",
        assist_name="Kenan Yildiz",
        minute="60",
        home_goals=4,
        away_goals=0,
        expect_photo=True,
    )

    correction_id, correction_was_photo, _, _ = send_goal_case(
        send=send,
        case="MARCATORE INIZIALE DA CORREGGERE — THIRD",
        player_name="Kerim Alajbegović",
        minute="70",
        home_goals=5,
        away_goals=0,
        kit="third",
        expect_photo=True,
    )
    corrected = render_goal(
        player_name="Pierre Kalulu",
        goal_type="goal",
        minute="70",
        home_goals=5,
        away_goals=0,
        scoring_team_id=HOME_ID,
        kit="third",
        event_key="simulation|corrected-scorer",
    )
    corrected_text = goal_caption(
        "MARCATORE CORRETTO — FOTO SOSTITUITA",
        "Pierre Kalulu",
        "",
        "goal",
        "70",
        5,
        0,
        HOME_ID,
    )
    if not corrected:
        raise RuntimeError("Correzione marcatore: nuova card non generata")
    if send:
        time.sleep(3)
        ok, _, is_photo = bot.replace_corrected_goal_message(
            correction_id, correction_was_photo, corrected_text, corrected
        )
        if not ok or not is_photo:
            raise RuntimeError("Correzione marcatore foto→foto fallita")
        time.sleep(1)
    else:
        print("OK correzione marcatore: foto rigenerata e sostituibile")

    photo_id, was_photo, _, _ = send_goal_case(
        send=send,
        case="CORREZIONE FOTO VERSO AUTOGOL",
        player_name="Nicolás González",
        minute="77",
        home_goals=6,
        away_goals=0,
        expect_photo=True,
    )
    own_goal_text = goal_caption(
        "CORRETTO IN AUTOGOL — CARD SENZA CALCIATORE",
        "Federico Dimarco",
        "",
        "own goal",
        "77",
        6,
        0,
        HOME_ID,
    )
    corrected_own_goal = render_goal(
        player_name="Federico Dimarco",
        goal_type="own goal",
        minute="77",
        home_goals=6,
        away_goals=0,
        scoring_team_id=HOME_ID,
        kit="home",
        event_key="simulation|corrected-own-goal",
    )
    if not corrected_own_goal or corrected_own_goal.player is not None:
        raise RuntimeError("Correzione autogol: card senza calciatore non generata")
    if send:
        ok, _, is_photo = bot.replace_corrected_goal_message(
            photo_id, was_photo, own_goal_text, corrected_own_goal
        )
        if not ok or not is_photo:
            raise RuntimeError("Correzione foto→card autogol fallita")
        time.sleep(1)
    else:
        print("OK correzione foto→card autogol senza calciatore")

    text_id, was_photo, _, _ = send_goal_case(
        send=send,
        case="MARCATORE PROVVISORIO ASSENTE",
        player_name="",
        minute="82",
        home_goals=7,
        away_goals=0,
        expect_photo=False,
    )
    restored = render_goal(
        player_name="Douglas Luiz",
        goal_type="goal",
        minute="82",
        home_goals=7,
        away_goals=0,
        scoring_team_id=HOME_ID,
        kit="home",
        event_key="simulation|restored-scorer",
    )
    restored_text = goal_caption(
        "MARCATORE AGGIUNTO — TESTO SOSTITUITO CON FOTO",
        "Douglas Luiz",
        "",
        "goal",
        "82",
        7,
        0,
        HOME_ID,
    )
    if not restored:
        raise RuntimeError("Correzione testo→foto: card non generata")
    if send:
        ok, _, is_photo = bot.replace_corrected_goal_message(
            text_id, was_photo, restored_text, restored
        )
        if not ok or not is_photo:
            raise RuntimeError("Correzione testo→foto fallita")
        time.sleep(1)
    else:
        print("OK correzione marcatore testo→foto")

    juve_own_goal = render_goal(
        player_name="Kenan Yildiz",
        goal_type="own goal",
        minute="85",
        home_goals=7,
        away_goals=1,
        scoring_team_id=AWAY_ID,
        kit="home",
        event_key="simulation|juventus-own-goal",
    )
    if juve_own_goal:
        raise RuntimeError("Autogol Juventus: non doveva essere generata alcuna card")

    shootout_goal = render_goal(
        player_name="Kenan Yildiz",
        goal_type="shootout goal",
        minute="120",
        home_goals=1,
        away_goals=1,
        scoring_team_id=HOME_ID,
        kit="third",
        event_key="simulation|shootout-goal",
    )
    if shootout_goal:
        raise RuntimeError("Lotteria rigori: non doveva essere generata una card GOAL")
    send_text(
        send,
        "<b>🧪 TEST ESPN — LOTTERIA DEI RIGORI</b>\n\n"
        "Juventus ✅ ✅ ❌ ✅\nInter ✅ ❌ ✅ ❌\n\n"
        "Nessuna card GOAL generata per i rigori della serie.",
    )

    friendly_goal = bot.prepara_grafica_goal(
        data_espn=espn_payload("home"),
        scorer_name="Kenan Yildiz",
        goal_type="goal",
        scoring_team_id=HOME_ID,
        minute="22",
        home_name=HOME_NAME,
        away_name=AWAY_NAME,
        home_id=HOME_ID,
        away_id=AWAY_ID,
        home_goals=1,
        away_goals=0,
        league_slug="club.friendly",
        league_name="Club Friendly",
        event_key="simulation|friendly-goal",
    )
    friendly_saved = bot.prepara_grafica_parata_rigore(
        data_espn=espn_payload("home"),
        penalty_event={
            "type": "penalty saved",
            "team_id": AWAY_ID,
            "player_name": "Lautaro Martínez",
        },
        goalkeeper_name="Guglielmo Vicario",
        minute="66",
        home_name=HOME_NAME,
        away_name=AWAY_NAME,
        home_id=HOME_ID,
        away_id=AWAY_ID,
        home_goals=1,
        away_goals=0,
        event_key="simulation|friendly-saved",
        league_slug="club.friendly",
        league_name="Club Friendly",
    )
    if friendly_goal or friendly_saved:
        raise RuntimeError("Amichevole: non doveva essere generata alcuna grafica")
    send_text(
        send,
        "<b>🧪 TEST ESPN — AMICHEVOLE</b>\n\n"
        "GOAL e rigore parato restano messaggi testuali: nessuna foto generata.",
    )

    saved_event = {
        "type": "penalty saved",
        "team_id": AWAY_ID,
        "player_name": "Lautaro Martínez",
    }
    rendered_saved = bot.prepara_grafica_parata_rigore(
        data_espn=espn_payload("home"),
        penalty_event=saved_event,
        goalkeeper_name="Guglielmo Vicario",
        minute="88",
        home_name=HOME_NAME,
        away_name=AWAY_NAME,
        home_id=HOME_ID,
        away_id=AWAY_ID,
        home_goals=7,
        away_goals=0,
        event_key="simulation|penalty-saved",
    )
    if not rendered_saved:
        raise RuntimeError("Rigore parato: card SAVED non generata")
    saved_text = (
        f"<b>🧪 TEST ESPN — RIGORE PARATO</b>\n"
        f"<b>RIGORE PARATO · 88' {bot.E_KICK}</b>\n\n"
        f"🧤 <i>{bot.fmt_player('Guglielmo Vicario')}</i>\n"
        f"{bot.E_PEN_KO} <i>{bot.fmt_player('Lautaro Martínez')}</i>"
    )
    if send:
        message_id, sent_as_photo = bot.send_telegram_saved_get_id(
            saved_text, rendered_saved.png
        )
        if not message_id or not sent_as_photo:
            raise RuntimeError("Invio SAVED a Bot JR non riuscito")
        time.sleep(1)
    else:
        print("OK rigore parato: card SAVED")

    missed_event = {
        "type": "penalty missed",
        "team_id": AWAY_ID,
        "player_name": "Lautaro Martínez",
    }
    if bot.prepara_grafica_parata_rigore(
        data_espn=espn_payload("home"),
        penalty_event=missed_event,
        goalkeeper_name="Guglielmo Vicario",
        minute="90",
        home_name=HOME_NAME,
        away_name=AWAY_NAME,
        home_id=HOME_ID,
        away_id=AWAY_ID,
        home_goals=7,
        away_goals=0,
        event_key="simulation|penalty-missed",
    ):
        raise RuntimeError("Rigore sbagliato: non doveva essere generata SAVED")
    send_text(
        send,
        f"<b>🧪 TEST ESPN — RIGORE SBAGLIATO</b>\n\n"
        f"{bot.E_PEN_KO} <i>{bot.fmt_player('Lautaro Martínez')}</i>\n\n"
        "Nessuna card SAVED: il rigore non risulta parato.",
    )

    send_text(
        send,
        "<b>✅ TEST ESPN SIMULATO COMPLETATO</b>\n\n"
        "Verificati: GOAL home/away/third, RIGORE, AUTOGOL a favore, "
        "marcatore senza foto, tre tipi di correzione, autogol Juventus senza card, "
        "lotteria senza GOAL, amichevole senza foto, rigore parato con SAVED e "
        "rigore sbagliato senza SAVED.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Invia davvero il replay a TELEGRAM_TO_BOT; senza flag valida soltanto.",
    )
    args = parser.parse_args()
    try:
        run(args.send)
    except Exception as exc:
        print(f"TEST FALLITO: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
