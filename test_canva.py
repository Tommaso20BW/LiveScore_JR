import os
import requests
import time
from base64 import b64encode
from nacl import encoding, public
from PIL import Image

# ==============================================================================
# CONFIGURAZIONE STRUTTURATA PER GITHUB SECRETS E CANVA
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

    print("🔄 Request di un Access Token temporaneo a Canva...")
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
# RECUPERO ASSET DA CANVA STANDARD
# ==============================================================================
def get_canva_image(access_token):
    """Avvia l'esportazione su Canva e scarica la pagina dei loghi"""
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {"type": "png", "pages": [PAGINA_TARGET]}
    }

    try:
        print("🎨 Richiesta generazione loghi a Canva...")
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
        if response.status_code not in [200, 201]: return None
        
        job_id = response.json().get("id") or response.json().get("job", {}).get("id")
        if not job_id: return None
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        
        for _ in range(20):
            time.sleep(3)
            check_res = requests.get(status_url, headers=headers, timeout=15)
            if check_res.status_code == 200:
                status_data = check_res.json()
                status_corrente = status_data.get("status") or status_data.get("job", {}).get("status")
                
                if status_corrente == "success":
                    urls_list = status_data.get("urls") or status_data.get("job", {}).get("urls")
                    download_url = urls_list[0] if urls_list else (status_data.get("url") or status_data.get("job", {}).get("url"))
                    if download_url:
                        print("📥 Download loghi superiore completato.")
                        return requests.get(download_url, timeout=20).content
                elif status_corrente == "failed": return None
    except Exception as e:
        print(f"❌ Errore recupero Canva: {e}")
    return None

# ==============================================================================
# CORE: COMPOSIZIONE A 3 LIVELLI (BACKGROUND -> GIOCATORE -> CANVA LOGHI)
# ==============================================================================
def genera_immagine_gol_test(squadra_segno, cognome_giocatore):
    print(f"\n⚡ Analisi evento: Gol di {cognome_giocatore} per {squadra_segno}")
    
    if squadra_segno.lower() != "juventus":
        print("➡️ Gol avversario. Il bot ignora l'evento.")
        return False

    nome_marcatore = cognome_giocatore.lower().strip()
    sfondo_path = f"assets/esultanze/{nome_marcatore}.png"
    bg_struttura_path = "assets/esultanze/background.png"  # Percorso aggiornato dentro esultanze

    # Verifica la presenza di entrambi i file locali necessari
    if not os.path.exists(sfondo_path):
        print(f"➡️ File '{sfondo_path}' non trovato. Salto.")
        return False
        
    if not os.path.exists(bg_struttura_path):
        print(f"❌ Errore: Manca lo sfondo base '{bg_struttura_path}' nella cartella assets/esultanze/.")
        return False

    print(f"📸 Asset locali pronti per {cognome_giocatore}. Chiamo Canva per i loghi...")
    
    token = get_valid_token()
    foto_canva_bytes = get_canva_image(token)
    if not foto_canva_bytes: return False

    canva_temp_path = "assets/canva_temp.png"
    with open(canva_temp_path, "wb") as f:
        f.write(foto_canva_bytes)

    try:
        print("🎨 Composizione avanzata dei 3 livelli in corso...")
        
        # 1. LIVELLO BASSO (Base): Carichiamo background.png
        immagine_finale = Image.open(bg_struttura_path).convert("RGBA")
        base_size = immagine_finale.size

        # 2. LIVELLO INTERMEDIO: Foto esultanza giocatore sopra il background
        foto_giocatore = Image.open(sfondo_path).convert("RGBA")
        if foto_giocatore.size != base_size:
            foto_giocatore = foto_giocatore.resize(base_size, Image.Resampling.LANCZOS)
            
        immagine_finale.paste(foto_giocatore, (0, 0), foto_giocatore)

        # 3. LIVELLO ALTO (Top): Scarichiamo i loghi da Canva, rimuovendo lo sfondo nero
        strato_loghi = Image.open(canva_temp_path).convert("RGBA")
        if strato_loghi.size != base_size:
            strato_loghi = strato_loghi.resize(base_size, Image.Resampling.LANCZOS)

        # Algoritmo Chroma Key progressivo per eliminare lo sfondo nero (#000000) di Canva
        dati_pixel = strato_loghi.getdata()
        nuovi_pixel = []
        
        soglia_nero = 45   
        soglia_pieno = 80  

        for pixel in dati_pixel:
            r, g, b, a = pixel
            luminosita = (r + g + b) // 3
            
            if luminosita <= soglia_nero:
                nuovi_pixel.append((0, 0, 0, 0)) # Sfondo trasparente
            elif luminosita >= soglia_pieno:
                nuovi_pixel.append((r, g, b, a)) # Elemento grafico originale
            else:
                # Anti-aliasing morbido per evitare bordi seghettati o aloni neri sporchi
                fattore = (luminosita - soglia_nero) / (soglia_pieno - soglia_nero)
                nuovo_alpha = int(a * fattore)
                nuovi_pixel.append((r, g, b, nuovo_alpha))
                
        strato_loghi.putdata(nuovi_pixel)

        # Incolliamo lo strato dei loghi pulito sopra l'unione (background + giocatore)
        immagine_finale.paste(strato_loghi, (0, 0), strato_loghi)

        # Esportazione finale in formato JPEG
        output_finale = f"assets/OUTPUT_{nome_marcatore}.jpg"
        immagine_finale.convert("RGB").save(output_finale, "JPEG", quality=95)
        
        print(f"✅ COMBINAZIONE RIUSCITA! Grafica finale generata in: {output_finale}")
        if os.path.exists(canva_temp_path): os.remove(canva_temp_path)
        return True

    except Exception as e:
        print(f"❌ Errore durante l'elaborazione Pillow: {e}")
        return False

def main():
    print("=== START BOT 3-LEVEL TEST ===")
    os.makedirs("assets/esultanze", exist_ok=True)
    genera_immagine_gol_test(squadra_segno="Juventus", cognome_giocatore="Vlahovic")

if __name__ == "__main__":
    main()
