"""Testi pronti da copiare su Bot JR dopo HALF / END / FULL TIME: uno per X e uno per Telegram/IG.

Ognuno arriva in un messaggio a parte, dentro un blocco che si copia con un tocco.
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


def message(title: str, text: str) -> str:
    """Messaggio da copiare: titolo e testo dentro un blocco (un tocco = copiato)."""
    return f"<b>{html.escape(title)}</b>\n<pre>{html.escape(text)}</pre>"


def send(post, chat_id, text: str, home: str, away: str) -> None:
    """Manda su Bot JR i due testi da copiare (X e Telegram/IG). Non ferma mai il live."""
    if not chat_id or not text:
        return
    try:
        pieces = (('𝕏 Testo per X', x_text(text, home, away)), ('✈️ Testo per Telegram / IG', plain(text)))
        for title, body in pieces:
            r = post('sendMessage', payload={'chat_id': chat_id, 'text': message(title, body),
                                             'parse_mode': 'HTML', 'disable_web_page_preview': True})
            if r is None or r.status_code != 200:
                log_line('WARN', 'TELEGRAM', f'Testo da copiare non inviato su Bot JR ({title})')
    except Exception as exc:  # noqa: BLE001 - i testi da copiare non devono fermare la diretta
        log_line('WARN', 'TELEGRAM', f'Testi da copiare non inviati: {type(exc).__name__}: {exc}')
