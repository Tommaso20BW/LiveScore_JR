import requests, os, base64
from datetime import datetime

CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
BOT_TOKEN           = os.getenv('TELEGRAM_TOKEN')
CHAT_ID             = os.getenv('TELEGRAM_TO')
CANVA_DESIGN_ID     = "DAHI3ytu6yQ"
CANVA_PAGE_THUMB_ID = "1785"
PAGINA_TARGET       = 11

try:
    from nacl import encoding, public
except ImportError:
    pass

def update_github_secret(secret_name, new_value):
    if not GH_PAT or not GITHUB_REPOSITORY:
        return False
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        pk = requests.get(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/public-key",
                          headers=headers, timeout=10).json()
        pub_key = public.PublicKey(pk["key"].encode("utf-8"), encoding.Base64Encoder)
        encrypted = base64.b64encode(public.SealedBox(pub_key).encrypt(new_value.encode())).decode()
        r = requests.put(f"https://api.github.com/repos/{GITHUB_REPOSITORY}/actions/secrets/{secret_name}",
                         headers=headers, json={"encrypted_value": encrypted, "key_id": pk["key_id"]}, timeout=10)
        return r.status_code in [201, 204]
    except Exception as e:
        print(f"❌ Errore update GitHub secret: {e}")
    return False

def get_valid_token():
    r = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
    }, timeout=15)
    if r.status_code == 200:
        tokens = r.json()
        if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
            print("🔄 Refresh token aggiornato su GitHub")
            update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"])
        return tokens["access_token"]
    print(f"❌ Errore token Canva: {r.text}")
    return None

def get_canva_image(access_token):
    if not access_token:
        return None
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        rp = requests.get(
            f"https://api.canva.com/rest/v1/designs/{CANVA_DESIGN_ID}/pages",
            headers=headers, timeout=15
        )
        pagina_num = None
        if rp.status_code == 200:
            for p in rp.json().get("items", []):
                thumb_url = p.get("thumbnail", {}).get("url", "")
                if f"/{CANVA_PAGE_THUMB_ID}/" in thumb_url:
                    pagina_num = p["page_number"]
                    print(f"✅ Pagina trovata: numero {pagina_num}")
                    break
        if not pagina_num:
            print(f"⚠️  Pagina con thumb_id={CANVA_PAGE_THUMB_ID} non trovata, uso PAGINA_TARGET={PAGINA_TARGET}")
            pagina_num = PAGINA_TARGET

        r = requests.post("https://api.canva.com/rest/v1/exports", headers=headers, json={
            "design_id": CANVA_DESIGN_ID, "format": {"type": "png", "pages": [pagina_num]}
        }, timeout=15)
        if r.status_code not in [200, 201]:
            print(f"❌ Errore export: {r.text}")
            return None
        job_data = r.json()
        job_id = job_data.get("id") or job_data.get("job", {}).get("id")
        if not job_id:
            return None
        status_url = f"https://api.canva.com/rest/v1/exports/{job_id}"
        import time
        time.sleep(3)
        for i in range(60):
            time.sleep(3)
            check = requests.get(status_url, headers=headers, timeout=15)
            if check.status_code == 200:
                d = check.json()
                stato = d.get("status") or d.get("job", {}).get("status")
                print(f"  Export status: {stato}")
                if stato == "success":
                    urls = d.get("urls") or d.get("job", {}).get("urls")
                    url_dl = urls[0] if urls else (d.get("url") or d.get("job", {}).get("url"))
                    if url_dl:
                        time.sleep(10)
                        return requests.get(url_dl, timeout=30).content
                elif stato == "failed":
                    print("❌ Export fallito")
                    return None
    except Exception as e:
        print(f"❌ Errore get_canva_image: {e}")
    return None

def send_telegram_with_photo(text, photo_bytes):
    if not photo_bytes:
        print("⚠️  Nessuna foto, invio solo testo")
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        print("Telegram status:", r.status_code)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    r = requests.post(url, data={"chat_id": CHAT_ID, "caption": text, "parse_mode": "HTML"},
                      files={"photo": ("matchday.png", photo_bytes)}, timeout=25)
    print("Telegram status:", r.status_code)

# --- MAIN ---
print("🔑 Ottengo token Canva...")
token = get_valid_token()
if not token:
    print("❌ Token non ottenuto, stop")
    exit(1)

print("🖼️  Scarico immagine Canva...")
foto = get_canva_image(token)
print(f"Foto ottenuta: {len(foto)} bytes" if foto else "❌ Foto non ottenuta")

print("📤 Invio su Telegram...")
send_telegram_with_photo(f"🧪 Test bot — {datetime.now().strftime('%H:%M:%S')}", foto)
