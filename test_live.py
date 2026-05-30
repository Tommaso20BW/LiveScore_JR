import json

# 1. Carichiamo il tuo file reale (PSG - Arsenal)
with open("summary.json", "r", encoding="utf-8") as f:
    dati = json.load(f)

# 2. SEZIONE CONFIGURAZIONE: Qui decidi tu cosa inventarti!
# Togli il cancelletto (#) solo alla riga che vuoi testare.

# --- Se vuoi simulare il Secondo Tempo:
STATO_INVENTATO = "STATUS_SECOND_HALF"
PERIODO_INVENTATO = 2

# --- Se vuoi simulare il Primo Tempo Supplementare (quando capiterà):
# STATO_INVENTATO = "STATUS_FIRST_OVERTIME_PERIOD"
# PERIODO_INVENTATO = 3

# --- Se vuoi simulare i Rigori:
# STATO_INVENTATO = "STATUS_SHOOTOUT"
# PERIODO_INVENTATO = 5


# 3. Forziamo ESPN a credere che la partita sia nel momento scelto da noi
try:
    dati["header"]["competitions"][0]["status"]["type"]["name"] = STATO_INVENTATO
    dati["header"]["competitions"][0]["status"]["period"] = PERIODO_INVENTATO
except KeyError:
    pass

# 4. LA LOGICA DEL TUO BOT: Vediamo se riconosce lo stato inventato
stato_nome = dati["header"]["competitions"][0]["status"]["type"]["name"]
periodo = dati["header"]["competitions"][0]["status"]["period"]

print("\n============================================")
print(f"STAI TESTANDO -> Stato: {stato_nome} | Periodo: {periodo}")
print("============================================")

if stato_nome == "STATUS_SECOND_HALF" and periodo == 2:
    print("✅ BOT: 'Ho capito che è il Secondo Tempo Regolamentare!'")

elif stato_nome == "STATUS_FIRST_OVERTIME_PERIOD" and periodo == 3:
    print("✅ BOT: 'Ho capito che siamo nel Primo Tempo Supplementare!'")

elif stato_nome == "STATUS_SHOOTOUT" and periodo == 5:
    print("✅ BOT: 'Ho capito che siamo ai Calci di Rigore!'")
else:
    print("❌ BOT: 'Questo stato non lo conosco, andrei in errore!'")
print("============================================\n")
