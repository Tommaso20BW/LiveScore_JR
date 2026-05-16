import os
import requests
import time
import sys

# ==============================================================================
# CONFIGURAZIONE (Recupera in automatico i tuoi Secret ambientali)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN') or "INSERISCI_QUI_IL_TOKEN_SE_PROVI_IN_LOCALE"
CHAT_ID = os.getenv('TELEGRAM_TO') or "INSERISCI_QUI_IL_CHAT_ID_SE_PROVI_IN_LOCALE"

# Rimuoviamo il controllo di match_state.json per la demo in modo che parta sempre!

# ==============================================================================
# SET EMOJI CUSTOM FORMATTATE IN HTML TELEGRAM
# ==============================================================================
E_BOLT = '<tg-emoji emoji-id="5778411071182217227">⚡️</tg-emoji>'
E_FLAG = '<tg-emoji emoji-id="5778434989855089204">🏁</tg-emoji>'
E_MIC  = '<tg-emoji emoji-id="5382013970905309819">🎙</tg-emoji>'
E_BALL = '<tg-emoji emoji-id="5373101763442255191">⚽️</tg-emoji>'
E_SUB  = '<tg-emoji emoji-id="5780817872070646566">🔄</tg-emoji>'
E_UP   = '<tg-emoji emoji-id="5449683594425410231">🔼</tg-emoji>'
E_DOWN = '<tg-emoji emoji-id="5447183459602669338">🔽</tg-emoji>'
E_RED  = '<tg-emoji emoji-id="5778513149669940622">🟥</tg-emoji>'
E_VAR  = '<tg-emoji emoji-id="5780478896071777414">📺</tg-emoji>'
E_PEN_OK = '<tg-emoji emoji-id="5427009714745517609">✅</tg-emoji>'
E_PEN_KO = '<tg-emoji emoji-id="5465665476971471368">❌</tg-emoji>'

E_COMP = '<tg-emoji emoji-id="5983047472354695060">🇮🇹</tg-emoji>'  # Coppa Italia
HOME_EMOJI = '<tg-emoji emoji-id="6028591382870888482">⚪️</tg-emoji>' # Juve
AWAY_EMOJI = '<tg-emoji emoji-id="5911036032035329229">🇮🇹</tg-emoji>' # Inter

HASHTAG = "#JuveInter"
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def main():
    print("🚀 DEMO SESTANTE AVVIATA - Invio forzato senza cache...")
    pausa = 3  

    # 1. INIZIO PARTITA
    send_telegram(f"<b>INIZIO PARTITA {E_BOLT}</b>\n\n{HOME_EMOJI} {HOME_NAME} - {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 2. GOL LIVE JUVENTUS
    send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-0 {AWAY_NAME} {AWAY_EMOJI}\n{E_BALL} <i>32’ D. Vlahovic</i>\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 3. GOL ANNULLATO
    send_telegram(f"<b>GOAL ANNULLATO {E_VAR}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-0 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 4. FINE PRIMO TEMPO
    send_telegram(f"<b>FINE PRIMO TEMPO {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-0 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 5. INIZIO SECONDO TEMPO
    send_telegram(f"<b>INIZIO SECONDO TEMPO {E_BOLT}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-0 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 6. CAMBIO
    send_telegram(f"<b>CAMBIO JUVENTUS {E_SUB}</b>\n\n{E_UP} A. Milik\n{E_DOWN} K. Yildiz\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 7. ROSSO
    send_telegram(f"<b>CARTELLINO ROSSO {E_RED}</b>\n\n🔚 <i>68’ N. Barella</i>\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 8. GOL INTER
    send_telegram(f"<b>GOAL {E_MIC}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n{E_BALL} <i>74’ L. Martinez</i>\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 9. FINE SECONDO TEMPO
    send_telegram(f"<b>FINE SECONDO TEMPO {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # 10. SUPPLEMENTARI
    send_telegram(f"<b>INIZIO PRIMO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)
    
    send_telegram(f"<b>FINE PRIMO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)
    
    send_telegram(f"<b>INIZIO SECONDO TEMPO SUPPLEMENTARE {E_BOLT}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)
    
    send_telegram(f"<b>FINE SECONDO TEMPO SUPPLEMENTARE {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} 1-1 {AWAY_NAME} {AWAY_EMOJI}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # RIGORI
    h_pens = [E_PEN_OK]
    a_pens = [E_PEN_OK]
    send_telegram(f"{HOME_EMOJI} {''.join(h_pens)}\n{AWAY_EMOJI} {''.join(a_pens)}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    h_pens.append(E_PEN_OK)
    a_pens.append(E_PEN_KO)
    send_telegram(f"{HOME_EMOJI} {''.join(h_pens)}\n{AWAY_EMOJI} {''.join(a_pens)}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    h_pens.append(E_PEN_OK)
    a_pens.append(E_PEN_OK)
    send_telegram(f"{HOME_EMOJI} {''.join(h_pens)}\n{AWAY_EMOJI} {''.join(a_pens)}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    h_pens.append(E_PEN_KO)
    a_pens.append(E_PEN_OK)
    send_telegram(f"{HOME_EMOJI} {''.join(h_pens)}\n{AWAY_EMOJI} {''.join(a_pens)}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    h_pens.append(E_PEN_OK)
    a_pens.append(E_PEN_KO)
    send_telegram(f"{HOME_EMOJI} {''.join(h_pens)}\n{AWAY_EMOJI} {''.join(a_pens)}\n\n{E_COMP} {HASHTAG}")
    time.sleep(pausa)

    # FINE
    score_string = "1 (4) - (2) 1"
    scorers_line = f"{E_BALL} <i>32’ D. Vlahovic // 74’ L. Martinez</i>\n"
    send_telegram(f"<b>FINE PARTITA {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} {score_string} {AWAY_NAME} {AWAY_EMOJI
