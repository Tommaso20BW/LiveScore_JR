import os
import requests
import time
from PIL import Image

# ==============================================================================
# CONFIGURAZIONE COMPLETA PER IL TEST OFFLINE LOCALMENTE
# ==============================================================================
# Incolla qui le tue chiavi reali per testare il funzionamento delle API Canva
CLIENT_ID = "IL_TUO_CANVA_CLIENT_ID"
CLIENT_SECRET = "IL_TUO_CANVA_CLIENT_SECRET"
CANVA_REFRESH_TOKEN = "IL_TUO_CANVA_REFRESH_TOKEN"

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 11

# ==============================================================================
# AUTOMAZIONE CANVA API
# ==============================================================================
def get_valid_token():
    """Genera un Access Token temporaneo usando il Refresh Token"""
    if not CANVA_REFRESH_TOKEN or CANVA_REFRESH_TOKEN == "IL_TUO_CANVA_REFRESH_TOKEN":
        print("❌ Errore: CANVA_REFRESH_TOKEN non configurato correttamente.")
        return None

    print("🔄 Richiesta di un Access Token temporaneo a Canva...")
    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            print("✅ Access Token generato con successo!")
            return res.json()["access_token"]
        else:
            print(f"❌ Errore nel recupero del token Canva: {res.text}")
            return None
    except Exception as e:
        print(f"❌ Errore connessione Canva OAuth: {e}")
        return None

def get_canva_image(access_token):
    """Richiede il rendering del file a Canva e restituisce i bytes dell'immagine"""
    if not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {"type": "png", "pages": [PAGINA_TARGET]}
    }

    try:
        print("🎨 Richiesta generazione immagine a Canva...")
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
        if response.status_code not in [200, 201]:
            print(f"❌ Errore avvio export Canva: {response.text}")
            return None
        
        job_id = response.json().get("id") or response.json().get("job", {}).get("id")
        if not job_id:
            return None
        
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        
        print("⏳ Attesa rendering della grafica su Canva...")
        for i in range(20):
            time.sleep(3)
            check_res = requests.get(status_url, headers=headers, timeout=15)
            if check_res.status_code == 200:
                status_data = check_res.json()
                status_corrente = status_data.get("status") or status_data.get("job", {}).get("status")
                print(f"   [Controllo {i+1}/20] Stato Canva: {status_corrente}")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    
                    if download_url:
                        print("📥 Download file PNG da Canva completato.")
                        img_res = requests.get(download_url, timeout=20)
                        return img_res.content
                        
                elif status_corrente == "failed":
                    print("❌ Il rendering su Canva è fallito.")
                    return None
                    
        print("❌ Timeout durante l'attesa del file da Canva.")
    except Exception as e:
        print(f"❌ Errore durante il recupero da Canva: {e}")
    return None

# ==============================================================================
# CORE: GENERAZIONE E SOVRAPPOSIZIONE GRAFICA 1:1
# ==============================================================================
def genera_immagine_gol_test(squadra_segno, cognome_giocatore):
    print(f"\n⚡ Elaborazione evento: Gol di {cognome_giocatore} ({squadra_segno})")
    
    # REGOLA 1: Se non ha segnato la Juventus, non fa nulla
    if squadra_segno.lower() != "juventus":
        print("➡️ Gol avversario. Il sistema ignora l'evento.")
        return False

    # Standardizziamo il nome del file esultanza locale
    nome_marcatore = cognome_giocatore.lower().strip()
    sfondo_path = f"assets/esultanze/{nome_marcatore}.png"

    # REGOLA 2: Se il giocatore è assente nell'elenco foto, non fa nulla
    if not os.path.exists(sfondo_path):
        print(f"➡️ File '{sfondo_path}' non trovato. Giocatore assente nell'elenco foto, salto l'invio.")
        return False

    print(f"📸 Sfondo trovato per {cognome_giocatore}. Procedo al recupero dei loghi da Canva...")
    
    # 1. Recuperiamo l'immagine trasparente aggiornata da Canva
    token = get_valid_token()
    if not token:
        print("❌ Impossibile procedere: Token Canva non valido.")
        return False
        
    foto_canva_bytes = get_canva_image(token)
    if not foto_canva_bytes:
        print("❌ Impossibile procedere: Immagine Canva non scaricata.")
        return False

    # Salviamo temporaneamente la sovrapposizione scaricata da Canva
    canva_temp_path = "assets/canva_temp.png"
    os.makedirs("assets", exist_ok=True)
    with open(canva_temp_path, "wb") as f:
        f.write(foto_canva_bytes)

    # 2. Avviamo la sovrapposizione 1:1 con Pillow
    try:
        print("🎨 Sovrapposizione livelli in corso (Formato 1:1)...")
        sfondo_giocatore = Image.open(sfondo_path).convert("RGBA")
        strato_loghi = Image.open(canva_temp_path).convert("RGBA")

        # Controllo di sicurezza sulle dimensioni delle due foto
        if sfondo_giocatore.size != strato_loghi.size:
            print(f"⚠️ Nota: Dimensioni diverse. Giocatore: {sfondo_giocatore.size} | Canva: {strato_loghi.size}")
            print("Adatto lo strato di Canva alle dimensioni dello sfondo del giocatore...")
            strato_loghi = strato_loghi.resize(sfondo_giocatore.size, Image.Resampling.LANCZOS)

        # Incolliamo combaciando perfettamente sul punto (0, 0)
        sfondo_giocatore.paste(strato_loghi, (0, 0), strato_loghi)

        # Salviamo l'output finale in locale
        output_finale = f"assets/OUTPUT_{nome_marcatore}.jpg"
        sfondo_giocatore.convert("RGB").save(output_finale, "JPEG", quality=95)
        
        print(f"✅ GRAFICA GENERATA CON SUCCESSO! Controlla il file: {output_finale}")
        
        # Pulizia del file temporaneo scaricato da Canva
        if os.path.exists(canva_temp_path):
            os.remove(canva_temp_path)
        return True

    except Exception as e:
        print(f"❌ Errore durante la sovrapposizione grafica: {e}")
        return False

# ==============================================================================
# FUNZIONE MAIN PER SIMULARE I VARI SCENARI DI TEST OFFLINE
# ==============================================================================
def main():
    print("=== AVVIO SIMULAZIONE DI TEST OFFLINE ===")
    
    # Assicuriamoci che la cartella degli asset esista per il test
    os.makedirs("assets/esultanze", exist_ok=True)
    
    # --- CASO 1: Segna la squadra avversaria (Deve bloccarsi subito) ---
    genera_immagine_gol_test(squadra_segno="Inter", cognome_giocatore="Martinez")
    
    # --- CASO 2: Segna la Juve ma il giocatore è assente (Deve bloccarsi subito) ---
    genera_immagine_gol_test(squadra_segno="Juventus", cognome_giocatore="GiocatoreInesistente")
    
    # --- CASO 3: Segna la Juve e il giocatore ESISTE (Esegue il flusso completo su Canva) ---
    genera_immagine_gol_test(squadra_segno="Juventus", cognome_giocatore="Vlahovic")

if __name__ == "__main__":
    main()
