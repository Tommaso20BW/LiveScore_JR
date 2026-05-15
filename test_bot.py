import os
import requests
import time

# Caricamento chiavi dai Secrets
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

# --- CONFIGURAZIONE SET EMOJI PRESET (TOMMASO STYLE) ---
E_BOLT = '<tg-emoji emoji-id="5778411071182217227">⚡️</tg-emoji>'
E_FLAG = '<tg-emoji emoji-id="5778434989855089204">🏁</tg-emoji>'
E_MIC  = '<tg-emoji emoji-id="5382013970905309819">🎙</tg-emoji>'
E_BALL = '<tg-emoji emoji-id="5373101763442255191">⚽️</tg-emoji>'
E_SUB  = '<tg-emoji emoji-id="5780817872070646566">🔄</tg-emoji>'
E_UP   = '<tg-emoji emoji-id="5449683594425410231">🔼</tg-emoji>'
E_DOWN = '<tg-emoji emoji-id="5447183459602669338">🔽</tg-emoji>'

# Emoji Eventi Speciali per il test del testo
E_YELLOW = '🟨'
E_RED    = '🟥'
E_VAR    = '🖥'
E_PENALTY= '🎯'

# Icone Squadre e Competizione (Esempio: Champions League)
E_JUVE = '<tg-emoji emoji-id="6028591382870888482">⚪️</tg-emoji>'
E_INTE = '<tg-emoji emoji-id="5911036032035329229">🇮🇹</tg-emoji>'
E_UEFA = '<tg-emoji emoji-id="6048563272855064239">🇪🇺</tg-emoji>'
HASHTAG = "#JuveInter"

def send_msg(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Errore di invio: {e}")
    time.sleep(2) # Pausa di 2 secondi per ricevere i messaggi in ordine cronologico

print("Avvio del test di cronaca totale sul tuo canale...")

# 1. FISCHIO D'INIZIO
send_msg(
    f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n"
    f"{E_JUVE} Juventus - Inter {E_INTE}\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 2. SEGNALAZIONE AMMONIZIONE (Giallo)
send_msg(
    f"<b>AMMONIZIONE {E_YELLOW}</b>\n\n"
    f"Giallo per Bremer al minuto 22’ per un intervento in ritardo.\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 3. PRIMO GOL LIVE (1-0)
send_msg(
    f"<b>GOAL {E_MIC}</b>\n\n"
    f"{E_JUVE} Juventus 1-0 Inter {E_INTE}\n"
    f"{E_BALL} <i>31’ K. Yildiz</i>\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 4. GOL ANNULLATO DA VAR
send_msg(
    f"<b>GOL ANNULLATO VAR {E_VAR}</b>\n\n"
    f"Annullata la rete del pareggio dell'Inter per una posizione di fuorigioco rilevata dal VAR al minuto 39’.\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 5. FINE PRIMO TEMPO
send_msg(
    f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n"
    f"{E_JUVE} Juventus 1-0 Inter {E_INTE}\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 6. INIZIO SECONDO TEMPO
send_msg(
    f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n"
    f"{E_JUVE} Juventus 1-0 Inter {E_INTE}\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 7. CAMBIO LIVE JUVENTUS (Doppia Sostituzione)
send_msg(
    f"<b>CAMBIO JUVENTUS {E_SUB}</b>\n\n"
    f"{E_UP} J. David, E. Zhegrova\n"
    f"{E_DOWN} D. Vlahovic, F. Conceição\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 8. RIGORE E SECONDO GOL LIVE (2-0)
send_msg(
    f"<b>GOAL {E_MIC} {E_PENALTY}</b>\n\n"
    f"{E_JUVE} Juventus 2-0 Inter {E_INTE}\n"
    f"{E_BALL} <i>31’ K. Yildiz, 72’ J. David (Rig.)</i>\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 9. ESPULSIONE (Rosso)
send_msg(
    f"<b>ESPULSIONE {E_RED}</b>\n\n"
    f"Inter in 10 uomini! Cartellino rosso diretto per un fallo grave di gioco al minuto 81’.\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 10. AUTOGOL LIVE (3-0)
send_msg(
    f"<b>GOAL {E_MIC}</b>\n\n"
    f"{E_JUVE} Juventus 3-0 Inter {E_INTE}\n"
    f"{E_BALL} <i>31’ K. Yildiz, 72’ J. David (Rig.), 88’ Autogol</i>\n\n"
    f"{E_UEFA} {HASHTAG}"
)

# 11. FINE PARTITA CON RIEPILOGO COMPLETO
send_msg(
    f"<b>FINE PARTITA {E_FLAG}</b>\n\n"
    f"{E_JUVE} Juventus 3-0 Inter {E_INTE}\n"
    f"{E_BALL} <i>31’ K. Yildiz, 72’ J. David (Rig.), 88’ Autogol</i>\n\n"
    f"{E_UEFA} {HASHTAG}"
)

print("Cronaca inviata! Corri a controllare su Telegram.")
