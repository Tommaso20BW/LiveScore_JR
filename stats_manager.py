import os
import requests
from playwright.sync_api import sync_playwright

def gestisci_invio_stats(match, bot_token, chat_id):
    status = match.get('fixture', {}).get('status', {}).get('short')
    
    # LOGICA: Invio solo se è HT (Fine 1T), FT (Fine Regolamentari) 
    # o se la partita è ufficialmente conclusa dopo i rigori (PEN)
    if status not in ["HT", "FT", "PEN"]:
        return

    # Se siamo in FT ma ci sono i supplementari, non inviare. 
    # API-Football di solito mette "AET" per supplementari finiti
    if status == "FT" and match.get('fixture', {}).get('status', {}).get('long') == "Extra Time":
        return

    print(f"📊 Generazione grafica per stato: {status}")
    
    # Qui inserisci il codice di Playwright per generare stats.png
    # ... (come visto nei messaggi precedenti) ...
    
    # Invio finale
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open("stats.png", "rb") as f:
        requests.post(url, data={'chat_id': chat_id, 'caption': f"📊 Statistiche {status}"}, files={'photo': f})
