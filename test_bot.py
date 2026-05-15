import os
import requests

E_FLAG = '<tg-emoji emoji-id="5778434989855089204">🏁</tg-emoji>'
E_BALL = '<tg-emoji emoji-id="5373101763442255191">⚽️</tg-emoji>'
E_UEFA = '<tg-emoji emoji-id="6048563272855064239">🇪🇺</tg-emoji>'
E_JUVE = '<tg-emoji emoji-id="6028591382870888482">⚪️</tg-emoji>'
E_INTE = '<tg-emoji emoji-id="5911036032035329229">🇮🇹</tg-emoji>'

BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

msg = (
    f"<b>FINE PARTITA {E_FLAG}</b>\n\n"
    f"{E_JUVE} Juventus 3-0 Inter {E_INTE}\n"
    f"{E_BALL} <i>14’ K. Yildiz, 42’ K. Yildiz, 78’ K. Yildiz</i>\n\n"
    f"{E_UEFA} #JuveInter"
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
print("Test inviato su Telegram!")
