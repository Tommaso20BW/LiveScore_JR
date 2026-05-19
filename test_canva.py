import os
import requests
import time
from base64 import b64encode
from nacl import encoding, public
from PIL import Image

# ==============================================================================
# CONFIGURAZIONE STRUTTURATA PER GITHUB SECRETS
# ==============================================================================
CLIENT_ID = os.environ.get("CANVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CANVA_CLIENT_SECRET")
CANVA_REFRESH_TOKEN = os.environ.get("CANVA_REFRESH_TOKEN")

CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 40

# ==============================================================================
# AUTOMAZIONE E AGGIORNAMENTO AUTOMATICO SECRETS GITHUB
# ==============================================================================
def update_github_secret(secret_name, new_value):
    """Cripta il nuovo token con PyNaCl e lo salva nei Secrets di GitHub via API"""
    github_pat = os.environ.get("GITHUB_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    
    if not github_pat or not repo:
        print("⚠️ Avviso: Credenziali GitHub non trovate in ambiente. Salto l'auto-aggiornamento.")
        return

    headers = {
        "Authorization": f"token {github_pat}",
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        # 1. Recupera la chiave pubblica della repository (necessaria per criptare)
        pub_key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
        res_key = requests.get(pub_key_url, headers=headers, timeout=15)
        if res_key.status_code != 200:
            print(f"❌ Impossibile recuperare la chiave pubblica di GitHub: {res_key.text}")
            return
        
        public_key_data = res_key.json()
        key_id = public_key_data["key_id"]
        public_key_b64 = public_key_data["key"]

        # 2. Cripta il token usando PyNaCl secondo lo standard richiesto da GitHub
        public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder)
        sealed_box = public.SealedBox(public_key)
        encrypted_value = sealed_box.encrypt(new_value.encode("utf-8"))
        encrypted_b64 = b64encode(encrypted_value).decode("utf-8")

        # 3. Invia il payload criptato per sovrascrivere il Secret esistente
        update_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
        payload = {
            "encrypted_value": encrypted_b64,
            "key_id": key_id
        }
        
        res_update = requests.put(update_url, headers=headers, json=payload, timeout=15)
        if res_update.status_code in [201, 204]:
            print(f"🔄 [AUTO-REFRESH] Secret '{secret_name}' aggiornato su GitHub!")
        else:
            print(f"❌ Errore nell'aggiornamento del Secret su GitHub: {res_update.text}")
            
    except Exception as e:
        print(f"❌ Errore durante l'interazione con le API di GitHub: {e}")


def get_valid_token():
    """Genera un Access Token e intercetta il nuovo Refresh Token generato da Canva"""
    if not CANVA_REFRESH_TOKEN:
        print("❌ Errore: CANVA_REFRESH_TOKEN non trovato nelle variabili d'ambiente.")
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
            dati = res.json()
            print("✅ Access Token generato con successo!")
            
            # Se Canva ha ruotato il token, lo script lo invia a GitHub
            if "refresh_token" in dati:
                nuovo_token = dati["refresh_token"]
                update_github_secret("CANVA_REFRESH_TOKEN", nuovo_token)
            
            return dati["access_token"]
        else:
            print(f"❌ Errore nel recupero del token Canva: {res.text}")
            return None
    except Exception as e:
        print(f"❌ Errore connessione Canva OAuth: {e}")
        return None

# ==============================================================================
# RECUPERO ASSET DA CANVA STANDARD (CON SFONDO NERO #000000 ESPORTATO)
# ==============================================================================
def get_canva_image(access_token):
    """Avvia l'esportazione su Canva e scarica la pagina con layout standard"""
    if not access_token:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {
            "type": "png", 
            "pages": [PAGINA_TARGET]
        }
    }

    try:
        print("🎨 Richiesta generazione asset grafici a Canva...")
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
        if response.status_code not in [200, 201]:
            print(f"❌ Errore avvio export Canva: {response.text}")
            return None
        
        job_id = response.json().get("id") or response.json().get("job", {}).get("id")
        if not job_id:
            return None
        
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        
        print("⏳ Attesa del rendering su Canva...")
        for i in range(20):
            time.sleep(3)
            check_res = requests.get(status_url, headers=headers, timeout=15)
            if check_res.status_code == 200:
                status_data = check_res.json()
                status_corrente = status_data.get("status") or status_data.get("job", {}).get("status")
                print(f"   [Controllo {i+1}/20] Stato rendering: {status_corrente}")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    
                    if download_url:
                        print("📥 Download del livello completato.")
                        img_res = requests.get(download_url, timeout=20)
                        return img_res.content
                        
                elif status_corrente == "failed":
                    print("❌ Il rendering su Canva è fallito. Controlla il progetto.")
                    return None
                    
        print("❌ Timeout durante l'attesa del file da Canva.")
    except Exception as e:
        print(f"❌ Errore durante il recupero da Canva: {e}")
    return None

# ==============================================================================
# CORE: FILTRI EVENTO E SOVRAPPOSIZIONE CON CHROMA KEY MORBIDO (ANTI-ALIASING)
# ==============================================================================
def genera_immagine_gol_test(squadra_segno, cognome_giocatore):
    print(f"\n⚡ Analisi evento: Gol di {cognome_giocatore} per {squadra_segno}")
    
    # 1. Filtro Squadra: Gestisce solo i gol della Juventus
    if squadra_segno.lower() != "juventus":
        print("➡️ Gol avversario. Il bot ignora l'evento.")
        return False

    nome_marcatore = cognome_giocatore.lower().strip()
    sfondo_path = f"assets/esultanze/{nome_marcatore}.png"

    # 2. Filtro File Locale: Verifica se abbiamo la foto del giocatore a catalogo
    if not os.path.exists(sfondo_path):
        print(f"➡️ File '{sfondo_path}' non trovato. Giocatore assente, salto l'invio senza crash.")
        return False

    print(f"📸 Sfondo trovato per {cognome_giocatore}. Recupero lo strato grafico da Canva...")
    
    # 3. Connessione API Canva
    token = get_valid_token()
    if not token:
        print("❌ Processo interrotto: Token Canva non recuperabile.")
        return False
        
    foto_canva_bytes = get_canva_image(token)
    if not foto_canva_bytes:
        print("❌ Processo interrotto: Immagine Canva vuota.")
        return False

    # Salvataggio temporaneo dello strato dei loghi scaricato
    canva_temp_path = "assets/canva_temp.png"
    os.makedirs("assets", exist_ok=True)
    with open(canva_temp_path, "wb") as f:
        f.write(foto_canva_bytes)

    # 4. Elaborazione Grafica Avanzata con Pillow
    try:
        print("🎨 Isolamento professionale dello sfondo nero con anti-aliasing...")
        sfondo_giocatore = Image.open(sfondo_path).convert("RGBA")
        strato_loghi = Image.open(canva_temp_path).convert("RGBA")

        # Autoresize protettivo dello strato Canva se differisce dalle esultanze
        if sfondo_giocatore.size != strato_loghi.size:
            strato_loghi = strato_loghi.resize(sfondo_giocatore.size, Image.Resampling.LANCZOS)

        # Trasformiamo lo strato in formato RGBA per manipolare i singoli canali
        dati_pixel = strato_loghi.getdata()
        nuovi_pixel = []
        
        # SOGLIE DI TOLLERANZA CHROMA KEY
        soglia_nero = 45   # Sotto questa luminosità, il pixel diventa trasparente al 100%
        soglia_pieno = 80  # Sopra questa luminosità, il pixel resta visibile al 100%

        for pixel in dati_pixel:
            r, g, b, a = pixel
            
            # Calcoliamo la luminosità media del pixel (da 0 a 255)
            luminosita = (r + g + b) // 3
            
            if luminosita <= soglia_nero:
                # Sfondo nero puro o scurissimo -> Trasparenza totale
                nuovi_pixel.append((0, 0, 0, 0))
            elif luminosita >= soglia_pieno:
                # Pixel chiaro (scritte, loghi, scudetti) -> Mantieni inalterato
                nuovi_pixel.append((r, g, b, a))
            else:
                # ZONA DI SFUMATURA (Bordi dei loghi): Calcoliamo un'Alpha graduale
                # Evita i bordi seghettati o gli aloni neri spessi
                fattore = (luminosita - soglia_nero) / (soglia_pieno - soglia_nero)
                nuovo_alpha = int(a * fattore)
                nuovi_pixel.append((r, g, b, nuovo_alpha))
                
        # Applichiamo la maschera pixel per pixel
        strato_loghi.putdata(nuovi_pixel)

        # Incolliamo la grafica sopra la foto del giocatore usando il nuovo canale Alpha
        sfondo_giocatore.paste(strato_loghi, (0, 0), strato_loghi)

        # Esportazione in JPG ad alta qualità pulendo il canale alpha per salvare il file finale
        output_finale = f"assets/OUTPUT_{nome_marcatore}.jpg"
        sfondo_giocatore.convert("RGB").save(output_finale, "JPEG", quality=95)
        
        print(f"✅ COMBINAZIONE RIUSCITA! Grafica ad alta definizione generata in: {output_finale}")
        
        # Pulizia del file temporaneo
        if os.path.exists(canva_temp_path):
            os.remove(canva_temp_path)
        return True

    except Exception as e:
        print(f"❌ Errore durante la manipolazione dell'immagine con Pillow: {e}")
        return False

# ==============================================================================
# FUNZIONE MAIN: SIMULAZIONE WORKFLOW
# ==============================================================================
def main():
    print("=== START BOT TEST WORKFLOW ===")
    os.makedirs("assets/esultanze", exist_ok=True)
    
    # Esegue il flusso reale cercando assets/esultanze/vlahovic.png
    genera_immagine_gol_test(squadra_segno="Juventus", cognome_giocatore="Vlahovic")

if __name__ == "__main__":
    main()
