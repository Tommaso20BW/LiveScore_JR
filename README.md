# ⚡ LiveScore JR

> Bot Telegram che segue **live, evento per evento**, le partite della Juventus — gira interamente su **GitHub Actions**, senza alcun server da mantenere.

---

## Cos'è

LiveScore JR monitora automaticamente ogni gara della Juventus e pubblica sul canale Telegram **@Juventus_Reborn** tutti gli aggiornamenti in tempo reale: fischio d'inizio, gol (con marcatore e assist), sostituzioni, cartellini rossi, rigori sbagliati, transizioni di stato (intervallo, supplementari, rigori) e card statistiche grafiche a metà e fine partita. Al fischio finale genera e invia una slide personalizzata via **Canva API**.

---

## Struttura del repository

```
LiveScore_JR/
├── juve_bot_espn.py             # Logica principale del bot (sorgente ESPN)
├── leagues.json                 # 214 competizioni ESPN: slug → { emoji, type }
├── teams.json                   # 677 squadre/nazionali: nome EN → [nome IT, forma breve]
├── stats.html                   # Template HTML per la card statistiche (renderizzato con Playwright)
├── texture_black.png            # Overlay texture kit home/away
├── texture_white.png            # Overlay texture kit third/default
└── .github/workflows/
    ├── main_espn.yml            # Workflow principale — Python 3.11, timeout 240 min
    └── canva_keep_alive.yml     # Rinnovo periodico del token Canva — Python 3.12
```

---

## Funzionalità

### Rilevamento automatico della partita
Il bot scansiona tutte le 214 leghe configurate in `leagues.json` e intercetta autonomamente la partita odierna (o quella del giorno successivo) che coinvolge la squadra monitorata. Non serve alcuna configurazione manuale per ogni match.

### Aggiornamenti in tempo reale

| Evento | Comportamento |
|---|---|
| **Gol** | Messaggio immediato al cambio del punteggio. Quando la fonte pubblica marcatore/assist, il messaggio viene **modificato via edit** — nessuno spam. Se la fonte corregge i dati in seguito, il bot li aggiorna silenziosamente. |
| **Sostituzioni** | Il bot aspetta qualche secondo per raccogliere cambi "gemelli" pubblicati in rapida successione. I cambi della stessa squadra nella stessa finestra vengono raggruppati in un unico messaggio, aggiornato via edit se ne arrivano altri. |
| **Cartellini rossi** | Notifica immediata con nome del giocatore e minuto. |
| **Rigori sbagliati** | Rilevamento dei penalty falliti o parati nei tempi regolamentari (esclusa la lotteria finale). |
| **Cambi di stato** | Avvisi per ogni transizione: inizio 1° tempo, intervallo, inizio 2° tempo, supplementari, rigori, fischio finale. |

### Card statistiche grafiche
A fine primo tempo, fine secondo tempo e al fischio finale viene inviata una card visuale (1620×1980 px) renderizzata da `stats.html` tramite Playwright/Chromium, con xG, possesso palla, tiri, tiri in porta, corner, falli, ammonizioni e passaggi.

### Tema maglia dinamico
La grafica si adatta al contesto della partita:

| Tema | Quando si applica |
|---|---|
| `home` | Juventus in casa, campionato |
| `away` | Juventus in trasferta, campionato |
| `third` | Coppe (Champions, Europa, Coppa Italia, Supercoppa…) |
| `default` | Partita senza la Juve o amichevole |

Il riconoscimento usa, in ordine: un override esplicito in `leagues.json`, il formato dello slug ESPN (`xxx.N` = campionato), e parole chiave di fallback.

### Slide finale Canva
Al fischio finale viene esportata e inviata una slide dal design Canva del canale. La slide viene inviata **solo se la Juventus è in campo** (controllo su `JUVE_ID = '111'`); per test su altre squadre viene inviato solo il messaggio testuale.

### Localizzazione italiana
I nomi di squadre e nazionali vengono tradotti tramite `teams.json` (677 voci), con forme brevi usate per gli hashtag. Le leghe hanno la propria emoji bandiera.

### Stato persistente su Gist
Lo stato della partita (gol rilevati, messaggi inviati, sostituzioni, cartellini, ecc.) è salvato su un Gist GitHub, così il bot sopravvive a un eventuale riavvio del workflow a partita in corso.

### Auto-rinnovo del token Canva
Il refresh token OAuth viene rigenerato e riscritto automaticamente nei GitHub Secrets ad ogni utilizzo. Il workflow `canva_keep_alive.yml` lo mantiene valido tra una partita e l'altra.

### Protezioni e guard
- Se il workflow parte a gara già terminata e il Gist è vuoto, il bot si spegne subito senza inviare nulla.
- Se il calcio d'inizio è a più di 60 minuti, il bot termina immediatamente (evita run inutili su GitHub Actions).

---

## Configurazione

### 1. Fork e Secrets

Vai in **Settings → Secrets and variables → Actions** e aggiungi:

| Secret | Descrizione |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot Telegram |
| `TELEGRAM_TO` | Chat ID del canale di destinazione |
| `GIST_ID` | ID del Gist usato come stato persistente |
| `GH_PAT` | Personal Access Token GitHub (scope: `gist` + `repo`) |
| `CANVA_CLIENT_ID` | Client ID dell'app Canva |
| `CANVA_CLIENT_SECRET` | Client Secret dell'app Canva |
| `CANVA_REFRESH_TOKEN` | Refresh token OAuth Canva (aggiornato automaticamente ad ogni uso) |

### 2. Crea il Gist di stato

Crea un nuovo Gist con un file chiamato `match_state.json` contenente `{}` e copia l'ID del Gist nella variabile `GIST_ID`.

### 3. Avvia il workflow

Il giorno della partita vai in **Actions → Run workflow** e lancia `main_espn.yml`. Il bot individua autonomamente la partita e rimane attivo fino al fischio finale (massimo 4 ore, limite di GitHub Actions).

> Il workflow accetta un input opzionale **`team_id`** (default `111`, Juventus) per testare il bot su un'altra squadra senza modificare il codice. Logo, tema kit e slide Canva restano comunque legati alla Juventus.

### 4. Mantieni valido il token Canva

Lancia occasionalmente il workflow **Canva Token Keep-Alive** per rinnovare il refresh token tra una partita e l'altra.

---

## Stack tecnico

`Python 3.11` · `requests` · `Playwright (Chromium)` · `Pillow` · `pynacl` · `GitHub Actions`

## Fonte dati

**ESPN** — endpoint pubblici `site.api.espn.com`, nessuna API key necessaria. Copertura di **214 competizioni** definite in `leagues.json` (campionati e coppe di tutto il mondo).

---

*Progetto amatoriale. Non affiliato a Juventus FC, Telegram, Canva o ESPN.*
