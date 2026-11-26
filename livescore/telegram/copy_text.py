"""Testi pronti da copiare su Bot JR dopo HALF / END / FULL TIME, senza scritte sopra:
prima il testo del canale così com'è (IG/Telegram, emoji personalizzate comprese), poi in risposta
il testo per X in un riquadro che si copia con un tocco.
Il testo per X segue i post di @Juventus_Reborn: squadre, marcatori e competizione con l'hashtag,
emoji normali, niente grassetto:

    FINE PARTITA 🏁

    #Juventus 4-1 #Omonia
    ⚽️ 37' #Cambiaso, 43' #Ekhator // 15' #Satka

    🇪🇺 #JuveOmonia
"""
import html
import re

from livescore.core.log import log_line

COPY_KINDS = ('half', 'end_of_90', 'full')


def plain(text: str) -> str:
    """HTML di Telegram -> testo semplice: emoji del canale con la loro emoji normale, niente tag."""
    text = re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', str(text or ''), flags=re.S)
    text = re.sub(r'<[^>]+>', '', text)
    lines = [line.rstrip() for line in html.unescape(text).split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def tag(name: str) -> str:
    """Nome -> hashtag come su X: "Kolo Muani" -> #KoloMuani, "I. Saibari" -> #Saibari."""
    words = [w for w in str(name or '').split() if not re.fullmatch(r"\w\.", w)]
    word = re.sub(r"[\s'’.\-]", '', ''.join(words))
    return f'#{word}' if word else ''


def _scorers(line: str) -> str:
    """⚽️ 37' Cambiaso, 43' Ekhator // 15' Satka  ->  ⚽️ 37' #Cambiaso, 43' #Ekhator // 15' #Satka"""
    def one(match):
        own = match.group(3) or ''
        return f"{match.group(1)} {tag(match.group(2))}{own}"
    return re.sub(r"(\d+(?:\+\d+)?['’]) ([^,/(]+?)( \(Autogol\))?(?=,|\s//|$)", one, line)


def x_text(text: str, home: str, away: str) -> str:
    """Testo della fase del canale -> testo per X (squadre e marcatori con l'hashtag)."""
    out = []
    for line in plain(text).split('\n'):
        if line.startswith('⚽'):
            line = _scorers(line)
        elif re.search(r'\d+(?: \(\d+\))?-(?:\(\d+\) )?\d+', line):
            for name in sorted(filter(None, {home, away}), key=len, reverse=True):
                line = re.sub(rf'(?<![#\w]){re.escape(name)}(?!\w)', tag(name), line)
        out.append(line)
    return '\n'.join(out)


def messages(text: str, home: str, away: str) -> tuple[str, str]:
    """(testo IG/Telegram come sul canale, testo per X nel riquadro)."""
    return text.strip(), f"<pre>{html.escape(x_text(text, home, away), quote=False)}</pre>"


def reply_to(message_id) -> dict:
    """Campi per mandare un messaggio in risposta (se quello e' sparito, parte lo stesso)."""
    return {'reply_parameters': {'message_id': int(message_id), 'allow_sending_without_reply': True}}


def send(post, chat_id, text: str, home: str, away: str) -> None:
    """Manda su Bot JR i testi da copiare (Telegram, poi X in risposta). Non ferma mai il live."""
    if not chat_id or not text:
        return
    try:
        tg_body, x_body = messages(text, home, away)
        r = post('sendMessage', payload={'chat_id': chat_id, 'text': tg_body,
                                         'parse_mode': 'HTML', 'disable_web_page_preview': True})
        if r is None or r.status_code != 200:
            log_line('WARN', 'TELEGRAM', 'Testi da copiare non inviati su Bot JR')
            return
        r = post('sendMessage', payload={'chat_id': chat_id, 'text': x_body, 'parse_mode': 'HTML',
                                         'disable_web_page_preview': True,
                                         **reply_to(r.json()['result']['message_id'])})
        if r is None or r.status_code != 200:
            log_line('WARN', 'TELEGRAM', 'Testo per X non inviato su Bot JR')
    except Exception as exc:  # noqa: BLE001 - i testi da copiare non devono fermare la diretta
        log_line('WARN', 'TELEGRAM', f'Testi da copiare non inviati: {type(exc).__name__}: {exc}')
