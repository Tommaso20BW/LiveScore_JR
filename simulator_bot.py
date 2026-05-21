import os
import sys
import time
import random
import json
import requests
from playwright.sync_api import sync_playwright

# Recupero dei Secret da GitHub Actions
BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_TO")

# Controllo di sicurezza iniziale per i Secret
if not BOT_TOKEN or not CHAT_ID:
    print("❌ ERRORE CRITICO: TELEGRAM_TOKEN o TELEGRAM_TO non configurati nei Secret di GitHub!")
    sys.exit(1)

# Classe per simulare l'andamento di una partita reale senza chiamare le API esterne
class PartitaSimulata:
    def __init__(self):
        self.stato = "1H"
        self.minuto = 0
        self.gol_juve = 0
        self.gol_avversario = 0
        self.cronologia_gol = []
        
    def aggiorna(self):
        if self.stato == "1H":
            self.minuto += 15
            if random.random() > 0.7:
                self.gol_juve += 1
                self.cronologia_gol.append(f"⚽ {self.minuto}' Gol Juventus!")
            if self.minuto >= 45:
                self.stato = "HT"
                
        elif self.stato == "HT":
            # Stato di transizione (Intervallo)
            self.stato = "2H"
            self.minuto = 46
            
        elif self.stato == "2H":
            self.minuto += 15
            if random.random() > 0.7:
                self.gol_avversario += 1
                self.cronologia_gol.append(f"⚽ {self.minuto}' Gol Avversario!")
            if self.minuto >= 90:
                self.stato = "FT"

    def genera_statistiche_finali(self):
        # Genera dati verosimili per il template HTML
        return {
            "risultato": f"{self.gol_juve} - {self.gol_avversario}",
            "juve_shots_on_goal": str(random.randint(3, 8)),
            "opp_shots_on_goal": str(random.randint(1, 6)),
            "juve_total_shots": str(random.randint(9, 18)),
            "opp_total_shots": str(random.randint(5, 12)),
            "juve_possession": str(random.randint(45, 65)),
            "opp_possession": str(random.randint(35, 55)),
            "juve_passes": str(random.randint(78, 88)),
            "opp_passes": str(random.randint(70, 82)),
            "marcatori": "\\n".join(self.cronologia_gol) if self.cronologia_gol else "Nessun gol"
        }

def invia_messaggio_testo(testo):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": testo, "parse_mode": "Markdown"})
        print(f"📡 Telegram Testo: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"❌ Errore invio testo: {e}")

def invia_grafica_canva_mock(stats):
    print("🎨 Simulazione generazione Grafica Canva Fine Partita...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    testo_canva = f"🖼️ *[GRAFICA CANVA FINE PARTITA]*\\n\\n🏁 JUVENTUS {stats['risultato']} AVVERSARIO\\n\\nMarcatori:\\n{stats['marcatori']}"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": testo_canva, "parse_mode": "Markdown"})
        print(f"📡 Telegram Canva Mock: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"❌ Errore invio Canva: {e}")

def genera_e_invia_stats(stats_data):
    print("📊 Avvio procedura rigida di generazione stats.png...")
    
    # Verifichiamo dove si trova il bot per evitare problemi di cartelle su GitHub
    path_corrente = os.getcwd()
    template_path = os.path.join(path_corrente, "template.html")
    output_image_path = os.path.join(path_corrente, "stats.png")
    
    if not os.path.exists(template_path):
        print(f"❌ ERRORE: {template_path} non trovato!")
        return

    # Usiamo Playwright in modo sincrono per stampare l'immagine basandoci sul template.html
    try:
        with sync_playwright() as p:
            print("🤖 Lancio di Chromium Headless...")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Carichiamo il file HTML locale tramite URL assoluto
            page.goto(f"file://{os.path.abspath(template_path)}")
            
            # Iniettiamo dinamicamente i dati simulati negli elementi DOM del template
            page.evaluate(f'document.getElementById("risultato").innerText = "{stats_data["risultato"]}";')
            page.evaluate(f'document.getElementById("j-sog").innerText = "{stats_data["juve_shots_on_goal"]}";')
            page.evaluate(f'document.getElementById("a-sog").innerText = "{stats_data["opp_shots_on_goal"]}";')
            page.evaluate(f'document.getElementById("j-ts").innerText = "{stats_data["juve_total_shots"]}";')
            page.evaluate(f'document.getElementById("a-ts").innerText = "{stats_data["opp_total_shots"]}";')
            page.evaluate(f'document.getElementById("j-pos").innerText = "{stats_data["juve_possession"]}";')
            page.evaluate(f'document.getElementById("a-pos").innerText = "{stats_data["opp_possession"]}";')
            page.evaluate(f'document.getElementById("j-pas").innerText = "{stats_data["juve_passes"]}";')
            page.evaluate(f'document.getElementById("a-pas").innerText = "{stats_data["opp_passes"]}";')
            
            # Regoliamo graficamente le barre di progressione inline via JS
            page.evaluate(f'document.getElementById("bar-l-sog").style.width = "{int(stats_data["juve_shots_on_goal"])*10}%";')
            page.evaluate(f'document.getElementById("bar-r-sog").style.width = "{int(stats_data["opp_shots_on_goal"])*10}%";')
            
            print("📸 Scatto dello screenshot in corso...")
            page.screenshot(path=output_image_path, full_page=True)
            browser.close()
            
        print(f"📸 Controllo fisico file: Esiste? {os.path.exists(output_image_path)}")
        
        if os.path.exists(output_image_path):
            print("📤 Spedizione del file stats.png a Telegram...")
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            
            # Forza l'apertura del file binario blindando la risorsa
            with open(output_image_path, "rb") as foto:
                files = {"photo": foto}
                data = {"chat_id": CHAT_ID, "caption": "📊 Statistiche definitive incontro (Simulazione)"}
                r = requests.post(url, files=files, data=data)
            
            print(f"📡 Telegram Immagine Stats: {r.status_code} - {r.text}")
        else:
            print("❌ ERRORE CRITICO: Il file stats.png non è stato generato sul disco.")
            
    except Exception as e:
        print(f"❌ ERRORE CRITICO DURANTE PLAYWRIGHT/INVIO: {str(e)}")

def main():
    partita = PartitaSimulata()
    print("🚀 Avvio del simulatore di partita ad alta velocità...")
    
    while True:
        partita.aggiorna()
        print(f"⏱️ Minuto: {partita.minuto} | Stato: {partita.stato} | Punteggio: {partita.gol_juve}-{partita.gol_avversario}")
        
        if partita.stato == "HT":
            invia_messaggio_testo(f"🏁 *FINE PRIMO TEMPO*\\nJuventus {partita.gol_juve} - {partita.gol_avversario} Avversario\\n\\n{partita.genera_statistiche_finali()['marcatori']}")
            print("⏳ Pausa tecnica di transizione tra i tempi...")
            time.sleep(5) # Simula l'intervallo velocemente
            
        elif partita.stato == "FT":
            stats_finali = partita.genera_statistiche_finali()
            
            # 1. Invia immediatamente il testo finale
            invia_messaggio_testo(f"🚨 *FISCHIO FINALE*\\nRisultato definitivo: Juventus {stats_finali['risultato']} Avversario")
            
            # 2. Richiesta esplicita: Attesa di esattamente 20 secondi dal fine partita
            print("⏳ Fischio finale rilevato. Attesa bloccante di 20 secondi richiesta dall'utente...")
            time.sleep(20)
            
            # 3. Invio della Grafica Canva Fine Partita
            invia_grafica_canva_mock(stats_finali)
            time.sleep(2) # Pausa di scarico di sicurezza prima del carico pesante di Playwright
            
            # 4. Generazione e invio dell'immagine delle statistiche
            genera_e_invia_stats(stats_finali)
            
            print("🛑 Processo completato con successo. Spegnimento di sicurezza.")
            time.sleep(5) # Lascia il tempo alle connessioni HTTP pendenti su GitHub di terminare
            sys.exit(0)
            
        time.sleep(2) # Velocità di crociera dei cicli di simulazione

if __name__ == "__main__":
    main()
