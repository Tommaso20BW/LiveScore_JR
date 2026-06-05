# ⚡ LiveScore JR

> Bot Telegram di copertura **live, evento per evento**, delle partite della Juventus — gira interamente su **GitHub Actions**, senza alcun server da mantenere.

---

## 📌 Panoramica

**LiveScore JR** segue in tempo reale ogni partita della Juventus e pubblica in automatico sul canale Telegram **@Juventus_Reborn** tutti gli eventi chiave: fischio d'inizio, gol, assist, sostituzioni, cartellini rossi, rigori sbagliati, cambi di periodo, statistiche grafiche di metà/fine tempo e una slide finale generata via **Canva API**.

Il bot esiste in **due varianti intercambiabili**, ciascuna con il proprio workflow GitHub Actions. Condividono la stessa logica di pubblicazione e si distinguono solo per la fonte dati:

| Variante | Script | Workflow | Fonte dati | API key |
|---|---|---|---|---|
| **ESPN** *(consigliata)* | `juve_bot_espn.py` | `main_espn.yml` | API pubblica ESPN (`site.api.espn.com`) | ❌ Non richiesta |
| **API-Football** | `juve_bot_api.py` | `main_api.yml` | API-Football (`v3.football.api-sports.io`) | ✅ Richiesta |

---

## 🗂️ Struttura del repository

```
LiveScore_JR/
├── juve_bot_espn.py          # Bot — variante ESPN (legge le leghe da leagues.json)
├── juve_bot_api.py           # Bot — variante API-Football (lista leghe interna)
├── leagues.json              # 214 leghe ESPN: slug → { emoji, type }
├── teams.json                # 677 squadre/nazionali: nome EN → [nome IT, forma breve]
├── stats.html                # Template HTML della card statistiche (reso con Playwright)
├── texture_black.png         # Overlay texture home/away
├── texture_white.png         # Overlay texture third/default
└── .github/workflows/
    ├── main_espn.yml         # Workflow variante ESPN (timeout 240 min)
    ├── main_api.yml          # Workflow variante API-Football (timeout 240 min)
    └── canva_keep_alive.yml  # Rinnovo periodico del token Canva
```

---

## ✨ Funzionalità

- **Rilevamento automatico della partita** — il bot cerca la gara odierna (e quella del giorno successivo) scorrendo tutte le leghe configurate e si aggancia non appena trova un incontro che coinvolge la squadra monitorata. Nessuna configurazione manuale per ogni match.

- **Cambi di periodo** — avvisi a ogni transizione di stato: 1° tempo, intervallo, 2° tempo, supplementari e rigori.

- **Gol in tempo reale** — il messaggio parte subito dopo la conferma del punteggio (breve attesa di stabilità per evitare falsi positivi). Quando la fonte pubblica marcatore e/o assist, il messaggio già inviato viene **modificato via edit**, senza spammare nuovi messaggi.

- **Correzione automatica del marcatore** — se la fonte corregge marcatore o assist dopo l'invio, il bot aggiorna silenziosamente il messaggio esistente.

- **Sostituzioni intelligenti** — al rilevamento di un cambio il bot attende qualche secondo e rilegge la fonte per raccogliere eventuali cambi "gemelli" pubblicati di seguito; i cambi della stessa squadra nella stessa finestra vengono raggruppati in un unico messaggio, aggiornato via edit se ne arrivano altri vicini.

- **Cartellini rossi** — notifica immediata con nome del giocatore e minuto.

- **Rigori sbagliati** — rilevamento dei penalty falliti o parati nei tempi regolamentari (esclusa la lotteria finale).

- **Statistiche grafiche** — card renderizzata da `stats.html` con Playwright/Chromium (1620×1980 px) e inviata a fine 1° tempo, fine 2° tempo e al fischio finale: xG, possesso, tiri, tiri in porta, corner, falli, ammonizioni, passaggi e altro.

- **Tema maglia dinamico** — la grafica adatta il kit in base al contesto: `home` (Juve in casa, campionato), `away` (Juve in trasferta, campionato), `third` (coppe) o `default` (partita senza la Juve, loghi ESPN). Il riconoscimento campionato/coppa usa un override esplicito in `leagues.json`, poi il formato dello slug, poi parole chiave di fallback.

- **Slide finale Canva** — al fischio finale viene esportata e inviata una slide personalizzata dal design Canva del canale.

- **Localizzazione in italiano** — i nomi di squadre e nazionali vengono tradotti tramite `teams.json` (677 voci), con una forma breve usata per gli hashtag; le leghe hanno la propria emoji bandiera.

- **Stato persistente su Gist** — lo stato della partita è salvato su un Gist, così il bot sopravvive a un eventuale riavvio del workflow durante la gara.

- **Auto-rinnovo del token Canva** — il refresh token OAuth viene rigenerato e riscritto automaticamente nei GitHub Secrets a ogni utilizzo; il workflow `canva_keep_alive.yml` (flag `ONLY_REFRESH_TOKEN`) lo mantiene valido tra una partita e l'altra.

- **Log leggibili** — ogni riga riporta il timestamp `[HH:MM:SS]` in fuso orario italiano; lo stato della partita viene loggato una volta al minuto invece che a ogni ciclo.

---

## ⚙️ Configurazione dei Secrets

In `Settings → Secrets and variables → Actions` della repository aggiungi:

| Secret | Descrizione | Variante |
|---|---|---|
| `TELEGRAM_TOKEN` | Token del bot Telegram | entrambe |
| `TELEGRAM_TO` | Chat ID del canale di destinazione | entrambe |
| `GIST_ID` | ID del Gist usato come stato persistente | entrambe |
| `GH_PAT` | Personal Access Token GitHub (per aggiornare Secrets e Gist) | entrambe |
| `CANVA_CLIENT_ID` | Client ID dell'app Canva | entrambe |
| `CANVA_CLIENT_SECRET` | Client Secret dell'app Canva | entrambe |
| `CANVA_REFRESH_TOKEN` | Refresh token OAuth Canva | entrambe |
| `API_KEY` | Chiave API-Football | solo variante API |

> La variante ESPN accetta inoltre un input opzionale **`team_id`** al lancio del workflow (default `111`, la Juventus): utile per testare il bot su un'altra squadra senza toccare il codice. La Juve resta comunque il riferimento per logo e tema kit.

---

## 🚀 Utilizzo

1. **Fai il fork** del repository.
2. Configura tutti i secret elencati sopra.
3. Crea un **Gist** con un file `match_state.json` contenente `{}` e copiane l'ID in `GIST_ID`.
4. Il giorno della partita, avvia il workflow desiderato da **`Actions → Run workflow`** (ESPN o API-Football).
5. Tieni il token Canva valido lanciando occasionalmente **`Canva Token Keep-Alive`**.

> Una volta avviato, il bot trova da solo la partita in corso (o la prossima del giorno) e attiva il ciclo di monitoraggio fino al fischio finale, entro il limite di 4 ore del workflow.

---

## 🛠️ Stack tecnico

`Python 3.11 / 3.12` · `requests` · `Playwright (Chromium)` · `Pillow` · `pynacl` · `GitHub Actions`

---

## 📡 Fonti dati

- **ESPN** — endpoint pubblici `site.api.espn.com`, nessuna API key necessaria; copertura di **214 competizioni** definite in `leagues.json` (campionati e coppe di tutto il mondo).
- **API-Football** — [api-sports.io](https://www.api-sports.io/), richiede un abbonamento e la relativa key.

---

*Progetto amatoriale. Non affiliato a Juventus FC, Telegram, Canva, ESPN o API-Football.*
