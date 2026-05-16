import os
import requests
import time
import sys

# ==============================================================================
# CONFIGURAZIONE (Recupera in automatico i tuoi Secret ambientali)
# ==============================================================================
BOT_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_TO')

# ==============================================================================
# EMOJI STANDARD (Rimosse le tg-emoji custom che bloccavano l'invio)
# ==============================================================================
E_BOLT = '⚡️'
E_FLAG = '🏁'
E_MIC  = '🎙'
E_BALL = '⚽️'
E_SUB  = '🔄'
E_UP   = '🔼'
E_DOWN = '🔽'
E_RED  = '🟥'
E_VAR  = '📺'
E_PEN_OK = '✅'
E_PEN_KO = '❌'

E_COMP = '🇮🇹'  
HOME_EMOJI = '⚪️⚫️' 
AWAY_EMOJI = '⚫️🔵' 

HASHTAG = "#JuveInter"
HOME_NAME = "Juventus"
AWAY_NAME = "Inter"

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Messaggio inviato con successo!")
    except Exception as e:
        print(f"❌ Errore invio Telegram: {e}")

def main():
    print("🚀 AVVIO SIMULAZIONE DI TEST GENERICA...")
    
    if not BOT_TOKEN or not CHAT_ID:
        print("❌ ERRORE: TELEGRAM_TOKEN o TELEGRAM_TO mancanti nei Secrets di GitHub!")
        sys.exit(1)
        
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

    # FINE PARTITA
    score_string = "1 (4) - (2) 1"
    scorers_line = f"{E_BALL} <i>32’ D. Vlahovic // 74’ L. Martinez</i>\n"
    send_telegram(f"<b>FINE PARTITA {E_FLAG}</b>\n\n{HOME_EMOJI} {HOME_NAME} {score_string} {AWAY_NAME} {AWAY_EMOJI}\n{scorers_line}\n{E_COMP} {HASHTAG}")
    
    print("🏁 Simulazione completata!")
    sys.exit(0)

if __name__ == "__main__":
    main()
