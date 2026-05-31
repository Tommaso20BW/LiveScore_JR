# ⚡ LiveScore JR
> Bot Telegram di copertura **live match-by-match** per la Juventus — costruito su GitHub Actions, senza server.
---
## 📌 Panoramica
**LiveScore JR** monitora in tempo reale ogni partita della Juventus e pubblica automaticamente sul canale Telegram **@Juventus_Reborn** tutti gli eventi chiave: fischio d'inizio, gol, sostituzioni, cartellini rossi, statistiche di metà e fine tempo, e la grafica finale via Canva API.
Il bot esiste in **due varianti intercambiabili**, ognuna con il proprio workflow GitHub Actions:
| Variante | File | Fonte dati |
|---|---|---|
| `main_api.yml` | `juve_bot_api.py` | API-Football (`v3.football.api-sports.io`) |
| `main_espn.yml` | `juve_bot_espn.py` | ESPN API pubblica (nessuna key richiesta) |
---
## 🗂️ Struttura del repository
```
LiveScore_JR/
├── juve_bot_api.py           # Bot versione API-Football
├── juve_bot_espn.py          # Bot versione ESPN
├── texture.png               # Overlay grafico applicato alle stats
└── .github/workflows/
    ├── main_api.yml          # Workflow API-Football (4h timeout)
    ├── main_espn.yml         # Workflow ESPN (4h timeout)
    └── canva_keep_alive.yml  # Rinnovo automatico token Canva
```
---
## ✨ Funzionalità
- **Inizio/fine periodi** — avvisi per ogni cambio di stato (1° tempo, intervallo, 2° tempo, supplementari, rigori)
- **Gol in tempo reale** — messaggio inviato immediatamente dopo la conferma del punteggio (15s), anche senza marcatore; il messaggio viene aggiornato via edit automatico non appena ESPN pubblica marcatore e/o assist, senza inviare nuovi messaggi
- **Assist** — riga `🅰️` aggiunta sotto il marcatore, editata in tempo reale se arriva in ritardo rispetto al gol
- **Correzione automatica del marcatore** — se ESPN corregge il marcatore o l'assist dopo l'invio, il bot modifica silenziosamente il messaggio già inviato
- **Sostituzioni raggruppate** — i cambi dello stesso minuto vengono aggregati in un unico messaggio per squadra
- **Cartellini rossi** — notifica immediata con nome e minuto
- **Rigori sbagliati** — rilevamento di penalty falliti e parati nei tempi regolamentari
- **Statistiche grafiche** — card HTML renderizzata con Playwright (1620×1980 px) inviata a metà tempo, fine 2° tempo e fischio finale; include xG, possesso, tiri, corner, falli, ammoniti, passaggi e altro
- **Grafica Canva** — al fischio finale viene esportata e inviata una slide personalizzata dal design Canva del canale
- **Stato persistente su Gist** — il bot sopravvive a eventuali riavvii del workflow durante la partita
- **Auto-rinnovo token Canva** — il refresh token viene aggiornato automaticamente nei GitHub Secrets ad ogni utilizzo
- **Log informativi** — ogni evento ha timestamp `[HH:MM:SS]`; il log di stato della partita esce una volta al minuto invece che ad ogni ciclo
---
## ⚙️ Configurazione dei Secrets
Aggiungi i seguenti secret nelle impostazioni della repository (`Settings → Secrets and variables → Actions`):
| Secret | Descrizione |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot Telegram |
| `TELEGRAM_TO` | Chat ID del canale di destinazione |
| `API_KEY` | Chiave API-Football *(solo variante API)* |
| `CANVA_CLIENT_ID` | Client ID dell'app Canva |
| `CANVA_CLIENT_SECRET` | Client Secret dell'app Canva |
| `CANVA_REFRESH_TOKEN` | Refresh token OAuth Canva |
| `GH_PAT` | Personal Access Token GitHub (per aggiornare secrets e Gist) |
| `GIST_ID` | ID del Gist usato come stato persistente |
---
## 🚀 Utilizzo
1. Fai il **fork** del repository
2. Configura tutti i secret elencati sopra
3. Crea un **Gist pubblico** con un file `match_state.json` contenente `{}`
4. Il giorno della partita, avvia manualmente il workflow desiderato da `Actions → Run workflow`
> Il bot rileva automaticamente la partita in corso (o la prossima in calendario) e aggancia il ciclo di monitoraggio senza ulteriori configurazioni.
---
## 🛠️ Stack tecnico
`Python 3.11/3.12` · `requests` · `Playwright (Chromium)` · `Pillow` · `pynacl` · `GitHub Actions`
---
## 📡 Fonte dati
- **Variante API**: [API-Football](https://www.api-sports.io/) — richiede abbonamento
- **Variante ESPN**: endpoint pubblici `site.api.espn.com` — nessuna API key necessaria, copertura di oltre 60 campionati
---
*Progetto amatoriale. Non affiliato con la Juventus FC, Telegram, Canva o ESPN.*
