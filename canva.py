import requests, os

CLIENT_ID           = os.getenv('CANVA_CLIENT_ID')
CLIENT_SECRET       = os.getenv('CANVA_CLIENT_SECRET')
CANVA_REFRESH_TOKEN = os.getenv('CANVA_REFRESH_TOKEN')
CANVA_DESIGN_ID     = "DAHI3ytu6yQ"

def get_valid_token():
    r = requests.post("https://api.canva.com/rest/v1/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": CANVA_REFRESH_TOKEN,
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET
    }, timeout=15)
    return r.json()["access_token"]

token = get_valid_token()
r = requests.get(
    f"https://api.canva.com/rest/v1/designs/{CANVA_DESIGN_ID}/pages",
    headers={"Authorization": f"Bearer {token}"}
)
print(r.status_code)
print(r.json())
