import json

# Il nostro scheletro di dati ESPN per i test
DATO_MOCK_ESPN = {
    "header": {
        "competitions": [
            {
                "status": {
                    "period": 1,
                    "displayClock": "00:00",
                    "type": {
                        "name": "STATUS_PRE_IN_PROGRESS"
                    }
                }
            }
        ]
    }
}

# 1. LISTA DI TUTTI GLI STATI CHE VOGLIAMO TESTARE INSIEME
stati_da_testare = [
    {"name": "STATUS_FIRST_HALF", "period": 1, "desc": "1° Tempo Regolamentare"},
    {"name": "STATUS_HALFTIME", "period": 1, "desc": "Intervallo Fine 1° Tempo"},
    {"name": "STATUS_SECOND_HALF", "period": 2, "desc": "2° Tempo Regolamentare"},
    {"name": "STATUS_FIRST_OVERTIME_PERIOD", "period": 3, "desc": "1° Tempo Supplementare Live"},
    {"name": "STATUS_OVERTIME_HALFTIME", "period": 3, "desc": "Intervallo Supplementari"},
    {"name": "STATUS_SECOND_OVERTIME_PERIOD", "period": 4, "desc": "2° Tempo Supplementare Live"},
    {"name": "STATUS_END_OF_OVERTIME", "period": 4, "desc": "Fine 120 minuti (Prima dei Rigori)"},
    {"name": "STATUS_SHOOTOUT", "period": 5, "desc": "Calci di Rigore Live"},
    {"name": "STATUS_FINAL_PEN", "period": 5, "desc": "Partita Finita ai Rigori"},
    {"name": "STATUS_FINAL", "period": 2, "desc": "Partita Finita nei 90 Minuti"}
]

print("\n========================================================")
print("             AVVIO TEST DI TUTTI GLI STATI LIVE         ")
print("========================================================\n")

# 2. IL CICLO CHE LI TESTA TUTTI INSIEME
for scenario in stati_da_testare:
    nome_test = scenario["name"]
    periodo_test = scenario["period"]
    descrizione = scenario["desc"]
    
    # Forziamo i dati nel mock per questo specifico scenario
    DATO_MOCK_ESPN["header"]["competitions"][0]["status"]["type"]["name"] = nome_test
    DATO_MOCK_ESPN["header"]["competitions"][0]["status"]["period"] = periodo_test
    
    # --- LA LOGICA DI CONTROLLO DEL TUO BOT ---
    status_obj = DATO_MOCK_ESPN["header"]["competitions"][0]["status"]
    stato_nome = status_obj["type"]["name"]
    periodo = status_obj["period"]
    
    # Verifica delle condizioni
    if stato_nome == "STATUS_FIRST_HALF" and periodo == 1:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_HALFTIME" and periodo == 1:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_SECOND_HALF" and periodo == 2:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_FIRST_OVERTIME_PERIOD" and periodo == 3:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_OVERTIME_HALFTIME" and periodo == 3:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_SECOND_OVERTIME_PERIOD" and periodo == 4:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_END_OF_OVERTIME" and periodo == 4:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_SHOOTOUT" and periodo == 5:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_FINAL_PEN" and periodo == 5:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    elif stato_nome == "STATUS_FINAL" and periodo == 2:
        print(f"✅ GESTITO -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo})")
        
    else:
        print(f"❌ ERRORE  -> {descrizione:<40} (Stato: {stato_nome} | Periodo: {periodo}) -> NON CONFIGURATO!")

print("\n========================================================")
print("                    TEST COMPLETATO                     ")
print("========================================================\n")
