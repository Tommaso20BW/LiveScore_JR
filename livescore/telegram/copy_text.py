"""Testi pronti da copiare su Bot JR dopo HALF / END / FULL TIME, in un solo messaggio:
"X" col testo per X in un blocco che si copia con un tocco, poi "IG/Telegram" col testo del canale
così com'è (emoji personalizzate comprese: dentro il blocco Telegram non le mostra).
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


def message(text: str, home: str, away: str) -> str:
    """Il messaggio da copiare: X (in un blocco) e IG/Telegram (come sul canale)."""
    return (f"<b>X</b>\n<pre>{html.escape(x_text(text, home, away))}</pre>\n\n"
            f"<b>IG/Telegram</b>\n{text.strip()}")


def send(post, chat_id, text: str, home: str, away: str) -> None:
    """Manda su Bot JR il messaggio coi testi da copiare. Non ferma mai il live."""
    if not chat_id or not text:
        return
    try:
        r = post('sendMessage', payload={'chat_id': chat_id, 'text': message(text, home, away),
                                         'parse_mode': 'HTML', 'disable_web_page_preview': True})
        if r is None or r.status_code != 200:
            log_line('WARN', 'TELEGRAM', 'Testi da copiare non inviati su Bot JR')
    except Exception as exc:  # noqa: BLE001 - i testi da copiare non devono fermare la diretta
        log_line('WARN', 'TELEGRAM', f'Testi da copiare non inviati: {type(exc).__name__}: {exc}')
