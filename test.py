import requests, os, base64

CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
GH_PAT              = os.getenv('GH_PAT')
GITHUB_REPOSITORY   = os.getenv('GITHUB_REPOSITORY')
CANVA_DESIGN_ID     = "DAHI3ytu6yQ"

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
        print(f"❌ Errore: {e}")
    return False

def get_valid_token():
    r = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
    }, timeout=15)
    if r.status_code == 200:
        tokens = r.json()
        if "refresh_token" in tokens and tokens["refresh_token"] != CANVA_REFRESH_TOKEN:
            update_github_secret("CANVA_REFRESH_TOKEN", tokens["refresh_token"])
        return tokens["access_token"]
    return None

token = get_valid_token()
r = requests.get(
    f"https://api.canva.com/rest/v1/designs/{CANVA_DESIGN_ID}/pages",
    headers={"Authorization": f"Bearer {token}"}
)
for p in r.json()["items"]:
    thumb_id = p["thumbnail"]["url"].split("/")[5]
    print(p["page_number"], thumb_id)
