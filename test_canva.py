import os
import requests
import time
from base64 import b64encode
from nacl import encoding, public
from PIL import Image

# Configurazione Secrets
CLIENT_ID = os.environ.get("CANVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CANVA_CLIENT_SECRET")
CANVA_REFRESH_TOKEN = os.environ.get("CANVA_REFRESH_TOKEN")
CANVA_DESIGN_ID = "DAHI3ytu6yQ"
PAGINA_TARGET = 40

def update_github_secret(secret_name, new_value):
    github_pat = os.environ.get("GITHUB_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not github_pat or not repo:
        print("⚠️ Avviso: Credenziali GitHub non trovate in ambiente. Salto l'auto-aggiornamento.")
        return
    headers = {"Authorization": f"token {github_pat}", "Accept": "application/vnd.github.v3+json"}
    try:
        pub_key_url = f"https://api.github.com/repos/{repo}/actions/secrets/public-key"
        res_key = requests.get(pub_key_url, headers=headers, timeout=15)
        if res_key.status_code != 200: return
        public_key_data = res_key.json()
        key_id = public_key_data["key_id"]
        public_key_b64 = public_key_data["key"]
        public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder)
        sealed_box = public.SealedBox(public_key)
        encrypted_value = sealed_box.encrypt(new_value.encode("utf-8"))
        encrypted_b64 = b64encode(encrypted_value).decode("utf-8")
        update_url = f"https://api.github.com/repos/{repo}/actions/secrets/{secret_name}"
        payload = {"encrypted_value": encrypted_b64, "key_id": key_id}
        res_update = requests.put(update_url, headers=headers, json=payload, timeout=15)
        if res_update.status_code in [201, 204]:
            print(f"🔄 [AUTO-REFRESH] Secret '{secret_name}' aggiornato su GitHub!")
    except Exception as e:
        print(f"❌ Errore aggiornamento secret: {e}")

def get_valid_token():
    if not CANVA_REFRESH_TOKEN: return None
    url = "https://api.canva.com/rest/v1/oauth/token"
    payload = {"grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    try:
        res = requests.post(url, data=payload, timeout=15)
        if res.status_code == 200:
            dati = res.json()
            if "refresh_token" in dati:
                update_github_secret("CANVA_REFRESH_TOKEN", dati["refresh_token"])
            return dati["access_token"]
        return None
    except:
        return None

def get_canva_image(access_token):
    if not access_token: return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    start_url = "https://api.canva.com/rest/v1/exports"
    payload = {
        "design_id": CANVA_DESIGN_ID,
        "format": {"type": "png", "pages": [PAGINA_TARGET]},
        "images_as_transparent_background": True
    }
    try:
        response = requests.post(start_url, headers=headers, json=payload, timeout=15)
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
                        return requests.get(download_url, timeout=20).content
                elif status_corrente == "failed": return None
    except:
        return None
    return None

def genera_immagine_gol_test(squadra_segno, cognome_giocatore):
    if squadra_segno.lower() != "juventus":
        print("➡️ Gol avversario. Ignorato.")
        return False

    nome_marcatore = cognome_giocatore.lower().strip()
    sfondo_path = f"assets/esultanze/{nome_marcatore}.png"

    if not os.path.exists(sfondo_path):
        print(f"➡️ File '{sfondo_path}' non trovato. Salto.")
        return False

    token = get_valid_token()
    foto_canva_bytes = get_canva_image(token)
    if not foto_canva_bytes: return False

    canva_temp_path = "assets/canva_temp.png"
    os.makedirs("assets", exist_ok=True)
    with open(canva_temp_path, "wb") as f:
        f.write(foto_canva_bytes)

    try:
        sfondo_giocatore = Image.open(sfondo_path).convert("RGBA")
        strato_loghi = Image.open(canva_temp_path).convert("RGBA")
        if sfondo_giocatore.size != strato_loghi.size:
            strato_loghi = strato_loghi.resize(sfondo_giocatore.size, Image.Resampling.LANCZOS)
        
        sfondo_giocatore.paste(strato_loghi, (0, 0), strato_loghi)
        output_finale = f"assets/OUTPUT_{nome_marcatore}.jpg"
        sfondo_giocatore.convert("RGB").save(output_finale, "JPEG", quality=95)
        print(f"✅ Grafica generata in: {output_finale}")
        if os.path.exists(canva_temp_path): os.remove(canva_temp_path)
        return True
    except Exception as e:
        print(f"❌ Errore Pillow: {e}")
        return False

def main():
    print("=== START BOT TEST WORKFLOW ===")
    os.makedirs("assets/esultanze", exist_ok=True)
    genera_immagine_gol_test("Juventus", "Vlahovic")

if __name__ == "__main__":
    main()
