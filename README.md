<div align="center">

# ⚡ LiveScore JR

**Bot Telegram che racconta in diretta, evento per evento, le partite della Juventus.**

Gira interamente su **GitHub Actions** — nessun server, nessun database, nessun costo di hosting.
**Completamente autonomo**: trova da solo le partite e si avvia 30 minuti prima del kickoff.

`Python 3.11` · `ESPN API` · `Playwright` · `Canva API` · `GitHub Gist` · `cron-job.org`

</div>

-----

## Indice

- [Cos'è](#cosè)
- [Come funziona](#come-funziona)
- [Avvio automatico (scheduler)](#avvio-automatico-scheduler)
- [Eventi tracciati](#eventi-tracciati)
- [Card statistiche](#card-statistiche)
- [Tema maglia dinamico](#tema-maglia-dinamico)
- [Slide finale Canva](#slide-finale-canva)
- [Architettura](#architettura)
- [Struttura del repository](#struttura-del-repository)
- [Configurazione](#configurazione)
- [Avvio](#avvio)
- [Stack tecnico](#stack-tecnico)
- [Limitazioni note](#limitazioni-note)

-----

## Cos'è

LiveScore JR monitora automaticamente la partita della Juventus e pubblica su un canale Telegram tutti gli aggiornamenti in tempo reale: calcio d'inizio, gol (con marcatore e assist), sostituzioni, cartellini rossi, rigori sbagliati, gol annullati dal VAR, **minuti di recupero**, transizioni di stato (intervallo, supplementari, lotteria dei rigori) e **card statistiche grafiche** a fine primo tempo e a fine partita. Al fischio finale, se in campo c'è la Juve, invia anche una **slide personalizzata** esportata dalla Canva API.

Tutta la logica vive in un unico script Python eseguito da un workflow GitHub Actions: il bot si avvia, trova la partita, la segue fino al triplice fischio e poi si spegne da solo. Grazie allo **scheduler automatico**, non serve nemmeno più avviarlo a mano: il sistema rileva da solo le partite in calendario e parte 30 minuti prima del fischio d'inizio.

-----

## Come funziona

```
   ┌──────────────────┐   POST /dispatches    ┌──────────────────────┐
   │   cron-job.org    │ ───────────────────▶ │   scheduler.yml       │
   │  (ogni 30 min,    │    (puntuale)         │  c'è una partita      │
   │   fascia partite) │                       │  Juve entro 60 min?   │
   └──────────────────┘                       └──────────┬───────────┘
                                                  sì, dispatch │
                                                              ▼
                ┌──────────────────────┐
                │   GitHub Actions      │  ← automatico (o manuale)
                │   main_espn.yml       │  attende fino a kickoff − 30′
                └──────────┬───────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │           juve_bot_espn.py            │
        │  1. trova la partita di oggi/domani   │
        │  2. polling del feed ESPN ogni ~6 s   │
        │  3. confronta lo stato e notifica     │
        └───┬────────────┬───────────┬──────────┘
            │            │           │
            ▼            ▼           ▼
        ┌────────┐  ┌─────────┐  ┌──────────┐
        │ ESPN   │  │ GitHub  │  │ Telegram │
        │ API    │  │ Gist    │  │ Bot API  │
        │ (dati) │  │ (stato) │  │ (output) │
        └────────┘  └─────────┘  └──────────┘
                         ▲
                    Canva API  → slide finale (solo Juve)
```

1. **Caccia alla partita** — all'avvio il bot scandaglia **304 competizioni** sull'API ESPN finché non trova la gara che coinvolge la Juve, oggi o domani. Le date sono calcolate sul fuso **US Eastern** (quello con cui ESPN indicizza gli eventi), così nemmeno le partite serali americane gli sfuggono.
1. **Battito ogni 6 secondi** — da lì in poi interroga il feed live di ESPN ogni ~6 s e ne ricostruisce lo stato completo: punteggio, eventi, statistiche, persino la maglia in campo.
1. **Notifica** — per ogni novità *reale* invia (o modifica) un messaggio Telegram in italiano.
1. **Persistenza** — dopo ogni cambiamento salva lo stato su un Gist: se il workflow si riavvia a partita in corso, il bot riparte esattamente da dove era. Se il Gist è temporaneamente irraggiungibile, il bot si **ferma** invece di ripartire da zero (evitando messaggi duplicati).
1. **Spegnimento** — al fischio finale invia statistiche e slide, resetta il Gist e si spegne da solo.

### Motore eventi multi-sorgente

ESPN non serve gli eventi su un piatto solo: li sparpaglia su **quattro feed diversi** — `commentary`, `keyEvents`, `scoringPlays` e `shootout` — spesso ripetendo lo stesso gol o cambio con minuti leggermente diversi e i giocatori in ordine invertito.

Il bot li fonde tutti in **un'unica linea temporale pulita**, abbattendo i doppioni su più livelli: per ID evento, per minuto + giocatore, e per *coppia* di giocatori nei cambi (così "Esce A, entra B" e "Entra B, esce A" diventano un solo cambio). E prima di cantare un gol aspetta 15 secondi e ri-controlla il punteggio: se ESPN "balla", niente notifiche false.

### Affidabilità dei messaggi

Ogni messaggio di periodo (calcio d'inizio, fine primo tempo, fine partita ecc.) viene registrato come inviato **solo dopo la conferma di Telegram** (200 OK + `message_id`). Se l'invio fallisce per un errore di rete o un rate limit (429), il bot riprova al ciclo successivo senza perdere eventi. Il rate limit 429 rispetta il campo `retry_after` restituito da Telegram.

-----

## Avvio automatico (scheduler)

Il cron nativo di GitHub Actions è inutilizzabile per un bot live: i trigger `schedule` partono con **ritardi anche di ore** (documentati e in peggioramento). Lo scheduler di LiveScore JR aggira il problema spostando la "sveglia" fuori da GitHub:

| Componente | Ruolo |
|------------|-------|
| **cron-job.org** | Sveglia esterna puntuale al minuto. Ogni 30 minuti, 24 ore su 24, chiama l'API GitHub e dispatcha `scheduler.yml`. |
| **`scheduler.yml`** | Check leggerissimo (~10 secondi). Esegue `scripts/scheduler_check.py` e, se serve, dispatcha il workflow principale passandogli l'orario del kickoff. |
| **`scripts/scheduler_check.py`** | Interroga i feed ESPN di **10 competizioni** (Serie A, Coppa Italia, Supercoppa Italiana, Champions, Europa League, Conference League, Supercoppa UEFA, Mondiale per Club, Coppa Intercontinentale, amichevoli) cercando la squadra con ID ESPN `111`. |
| **`main_espn.yml`** | Riceve l'input `kickoff` e **attende fino a 30 minuti prima** del calcio d'inizio, poi avvia il bot. |

### Logica della finestra di dispatch

Tutti i calcoli avvengono in **UTC** (ESPN, GitHub e lo script parlano la stessa lingua oraria: nessun problema di ora legale).

- kickoff a **più di 60 minuti** → nessuna azione, si riprova al check successivo;
- kickoff **entro 60 minuti** → dispatch del bot, che dorme fino a *kickoff − 30′*;
- partita **già iniziata da meno di 100 minuti** → **recupero d'emergenza**: il bot parte subito (utile se un check precedente è saltato per un downtime).

La finestra di 60 minuti (intervallo cron 30′ + anticipo 30′) garantisce che almeno un check "catturi" ogni partita, qualunque sia l'orario del kickoff.

### Protezioni

- **Anti-doppio avvio** — prima del dispatch, lo scheduler verifica via API che non ci sia già un run del bot attivo o in coda; in più il workflow principale ha un `concurrency group` dedicato.
- **Cronologia pulita** — a fine check lo scheduler **cancella automaticamente tutti i propri run precedenti** dalla tab Actions: resta visibile solo l'ultimo (un run non può auto-eliminarsi mentre gira, limite di GitHub). I run del bot principale non vengono toccati.
- **Feed irraggiungibile** — se un feed ESPN non risponde, lo script lo segnala nei log e prosegue con le altre competizioni.

-----

## Eventi tracciati

| Evento                  | Comportamento |
|-------------------------|---------------|
| **Calcio d'inizio**     | Messaggio all'inizio del primo tempo. |
| **Gol**                 | Notifica immediata al cambio del punteggio (con conferma a 15 s per evitare falsi positivi). Quando ESPN pubblica marcatore e assist, il messaggio viene **modificato via edit** — niente spam. Se la fonte corregge i dati in seguito, il bot aggiorna il messaggio silenziosamente. Gestisce autogol *(Autogol)* e rigori *(Rig.)*. |
| **Gol annullato**       | Se il punteggio cala, attende 120 s di conferma: se l'annullamento è reale invia *GOAL ANNULLATO* e ripulisce lo stato; se era un errore di ESPN, cancella l'eventuale messaggio di annullamento già inviato. |
| **Sostituzioni**        | Attende qualche secondo per raggruppare i cambi "gemelli" della stessa squadra nella stessa finestra di minuti in un unico messaggio, aggiornato via edit se ne arrivano altri. Robusto contro i duplicati provenienti da fonti ESPN diverse. |
| **Cartellini rossi**    | Notifica immediata (rosso diretto e doppia ammonizione) con giocatore e minuto. |
| **Rigori sbagliati**    | Rileva penalty falliti o parati nei tempi regolamentari (esclusa la lotteria finale). Dedup per giocatore + esito con tolleranza ±3' sul minuto: cambia ESPN il minuto 44'→45', il bot non manda un secondo messaggio. |
| **Minuti di recupero**  | Quando ESPN annuncia i minuti di recupero nel commentary (es. *"4 minutes of added time"*), il bot invia un messaggio dedicato per ciascun periodo (1° tempo, 2° tempo, supplementari). Un messaggio per periodo, dedup persistito nel Gist. |
| **Lotteria dei rigori** | Tracciamento colpo per colpo con sequenza di ✅/❌ per entrambe le squadre. |
| **Transizioni di stato**| Fine primo tempo, inizio secondo tempo, fine regolamentari, inizio/fine di ciascun tempo supplementare, fine supplementari, rigori, fine partita. |
| **Recupero (catch-up)** | Se il bot parte a partita già in corso con lo stato vuoto, ricostruisce e annuncia i gol già avvenuti prima di passare al rilevamento live. |

-----

## Card statistiche

A **fine primo tempo**, a **fine secondo tempo** (quando si va ai supplementari) e a **fine partita**, il bot genera e invia una card grafica.

Le statistiche vengono inviate **2 minuti dopo** il cambio di stato (HT / fine regolamentari / FT) tramite una **coda non bloccante** persistita nel Gist: il bot continua a rilevare gol, cambi e cartellini durante l'attesa. Se il bot crasha nel frattempo, al riavvio le stats vengono automaticamente riprogrammate.

Il flusso di rendering: il template `stats.html` viene riempito con i dati della gara, renderizzato a **1620×2160 px** da **Playwright/Chromium**, e infine sovrapposto a una texture (`texture_black.png` per home/away, `texture_white.png` per third/default) con **Pillow**.

Le 12 statistiche mostrate sono:

> Possesso palla · Tiri in porta · Tiri totali · Tiri bloccati · Corner · Fuorigioco · Falli · Ammoniti · Espulsi · Parate · Passaggi totali · Precisione passaggi

I valori vengono letti dal box score ESPN della partita, attingendo a più sezioni del feed (`boxscore.teams`, `header.competitions[].competitors`) per coprire qualsiasi competizione.

-----

## Tema maglia dinamico

La grafica della card si adatta al contesto della partita:

| Tema      | Maglia Juve                              | Stile                              |
|-----------|------------------------------------------|------------------------------------|
| `home`    | Prima maglia                             | Bianco/nero a strisce, accenti oro |
| `away`    | Seconda maglia                           | Rosa con dettagli neri             |
| `third`   | Terza maglia                             | Nero con dettagli oro              |
| `default` | Partita senza la Juve, oppure amichevole | Colori reali delle due squadre     |

Il tema non è cablato a tavolino: il bot legge da ESPN la maglia che la Juve **indossa davvero** in quella specifica partita (`kit_analyzer.py`), così la card riproduce kit e colori reali visti in campo. Per il tema `default` i colori delle due squadre diventano anche i bagliori e i gradienti dello sfondo.

-----

## Slide finale Canva

Al triplice fischio il bot esporta una slide dal design Canva del canale tramite la **Canva REST API** (OAuth) e la allega al messaggio di fine partita.

La slide viene inviata **solo se la Juventus è effettivamente in campo** (controllo sull'ID ESPN `111`). Per i test su altre squadre viene inviato solo il messaggio testuale. Il refresh token OAuth viene **rinnovato e riscritto automaticamente** nei GitHub Secrets a ogni utilizzo, così non scade mai tra una partita e l'altra.

> **Attenzione:** se il rinnovo del token riesce ma il salvataggio del GitHub Secret fallisce, il bot invia un **avviso immediato su Telegram** con istruzioni per aggiornare il secret a mano. Senza intervento, i run successivi non riuscirebbero a generare la slide.

-----

## Architettura

| Componente              | Ruolo |
|-------------------------|-------|
| **cron-job.org**        | Trigger esterno puntuale: ogni 30 minuti dispatcha lo scheduler via API GitHub (il cron nativo di Actions ha ritardi di ore). |
| **ESPN API**            | Fonte dati. Endpoint pubblici `site.api.espn.com`, **nessuna API key**. `scoreboard` per trovare la partita, `summary` per il live. |
| **GitHub Gist**         | Stato persistente (`match_state.json`): gol rilevati, ID dei messaggi inviati, sostituzioni, cartellini, coda stats, recuperi annunciati, ecc. Permette al bot di sopravvivere a un riavvio del workflow. Letto con 3 retry automatici; in caso di errore persistente il bot si ferma (non riparte da zero). |
| **Telegram Bot API**    | Output. Invio, modifica (`editMessageText`) e cancellazione dei messaggi. Rate limit 429 rispettato tramite `retry_after`. |
| **Canva API**           | Esportazione della slide finale via OAuth. |
| **Playwright + Pillow** | Rendering della card statistiche da HTML a PNG, con overlay texture. Import lazy: caricati solo quando serve, non dal keep-alive. |
| **pynacl**              | Cifratura per aggiornare i GitHub Secrets (rotazione del refresh token Canva). |
| **requests.Session**    | Sessione HTTP condivisa con retry automatici (3×, backoff) sui GET verso ESPN, GitHub e Canva. I POST Telegram non vengono ritentati in automatico per evitare doppi invii. |

-----

## Struttura del repository

```
LiveScore_JR/
├── juve_bot_espn.py             # Logica principale del bot
├── kit_analyzer.py              # Determina kit e colori maglie dai dati ESPN
├── leagues.json                 # 304 competizioni: slug → { emoji, type? }
├── teams.json                   # 677 squadre/nazionali: nome EN → [nome IT, forma breve]
├── stats.html                   # Template HTML della card statistiche
├── requirements.txt             # Dipendenze Python (condiviso dai workflow)
├── texture_black.png            # Overlay texture per i kit home/away
├── texture_white.png            # Overlay texture per i kit third/default
├── scripts/
│   └── scheduler_check.py       # Check partite Juve su 10 competizioni ESPN
└── .github/workflows/
    ├── main_espn.yml            # Workflow principale (Python 3.11, timeout 240 min)
    ├── scheduler.yml            # Scheduler: check + dispatch + pulizia cronologia
    └── canva_keep_alive.yml     # Rinnovo del token Canva (Python 3.12, solo requests+pynacl)
```

-----

## Configurazione

### 1. Fork e Secrets

In **Settings → Secrets and variables → Actions** aggiungi:

| Secret                | Descrizione |
|-----------------------|-------------|
| `TELEGRAM_TOKEN`      | Token del bot Telegram. |
| `TELEGRAM_TO`         | Chat ID del canale di destinazione. |
| `GIST_ID`             | ID del Gist usato come stato persistente. |
| `GH_PAT`              | Personal Access Token GitHub (scope `gist` + `repo`). Serve sia per il Gist sia per riscrivere il refresh token Canva nei Secrets. |
| `CANVA_CLIENT_ID`     | Client ID dell'app Canva. |
| `CANVA_CLIENT_SECRET` | Client Secret dell'app Canva. |
| `CANVA_REFRESH_TOKEN` | Refresh token OAuth Canva (aggiornato automaticamente a ogni uso). |

### 2. Crea il Gist di stato

Crea un Gist con un file `match_state.json` contenente `{}` e copia l'ID del Gist nel secret `GIST_ID`.

### 3. Configura lo scheduler automatico

1. **PAT fine-grained** — crea un token in *Settings → Developer settings → Personal access tokens → Fine-grained tokens*, limitato a questo repository, con permesso **Actions: Read and write** (Contents: Read-only viene aggiunto in automatico). Questo token vive solo su cron-job.org e serve unicamente a "bussare" allo scheduler.
2. **cron-job.org** — crea un cronjob con:
   - **URL**: `https://api.github.com/repos/<utente>/LiveScore_JR/actions/workflows/scheduler.yml/dispatches`
   - **Metodo**: `POST` · **Body**: `{"ref":"main"}`
   - **Headers**: `Authorization: Bearer <PAT>` · `Accept: application/vnd.github+json` · `User-Agent: livescore-cron`
   - **Schedule**: ogni 30 minuti, tutto il giorno
3. **Test** — premi *Test run*: risposta attesa **204** e, entro pochi secondi, il run "Match Scheduler" compare nella tab Actions.

### 4. (Opzionale) Personalizza design Canva e squadra

Nel codice puoi adattare:

- `CANVA_DESIGN_ID` e `PAGINA_TARGET` — il design e la pagina da esportare come slide finale.
- `JUVE_ID` — l'ID ESPN usato per il branding (logo + tema kit). È volutamente separato da `TEAM_ID`, così una partita senza la Juve resta sul tema `default` con i loghi ESPN.
- `LEAGUES` in `scripts/scheduler_check.py` — le competizioni controllate dallo scheduler.
- `KEEP` in `scheduler.yml` — quanti run dello scheduler tenere in cronologia (default `0`: resta visibile solo l'ultimo).

-----

## Avvio

### Automatico (default)

Non devi fare nulla: nei giorni di partita lo scheduler rileva il match e il bot parte da solo **30 minuti prima del kickoff**, resta attivo fino al fischio finale e si spegne. Se un check dovesse saltare (downtime di cron-job.org o di ESPN), il check successivo recupera: il bot viene avviato fino a 100 minuti dopo il kickoff a partita in corso.

### Manuale (sempre disponibile)

Da **Actions → Juventus Live Score - ESPN → Run workflow**:

- Input opzionale **`kickoff`** (ISO 8601 UTC, es. `2026-08-23T18:45:00Z`): il bot attende fino a 30 minuti prima di quell'orario. Lasciato vuoto, parte subito come sempre.
- Input opzionale **`team_id`** (default `111`, Juventus): permette di testare il bot su un'altra squadra senza toccare il codice. Logo, tema kit e slide Canva restano comunque legati alla Juve.

**Guard di sicurezza** (per non sprecare minuti di GitHub Actions):

- Se il workflow parte a partita **già conclusa** e il Gist è vuoto → si spegne subito senza inviare nulla.
- Se mancano **più di 60 minuti** al calcio d'inizio → termina immediatamente. *(Con l'avvio automatico il problema non si pone: lo step di attesa fa partire il bot esattamente a kickoff − 30′.)*
- Se il **Gist è irraggiungibile** dopo 3 retry → il bot si ferma con `exit(1)` per evitare di reinviare messaggi già pubblicati.

**Token Canva:** lancia ogni tanto il workflow **Canva Token Keep-Alive** per rinnovare il refresh token nei periodi senza partite. Il keep-alive installa solo `requests` e `pynacl` (niente Playwright/Chromium), quindi gira in pochi secondi.

-----

## Stack tecnico

`Python 3.11` · `requests` · `Playwright (Chromium)` · `Pillow` · `pynacl` · `GitHub Actions` · `cron-job.org`

**Fonte dati:** ESPN — endpoint pubblici `site.api.espn.com`, nessuna API key. Copertura di **304 competizioni** definite in `leagues.json` (campionati e coppe di tutto il mondo). **Localizzazione italiana** di 677 squadre e nazionali tramite `teams.json`, con forme brevi usate per gli hashtag.

-----

## Limitazioni note

- **Dipendenza da cron-job.org per l'avvio automatico.** Se il servizio esterno è in downtime, il check salta; il sistema recupera al check successivo (dispatch d'emergenza fino a 100 minuti dopo il kickoff). L'avvio manuale resta sempre disponibile come fallback.
- **Copertura amichevoli parziale.** Il feed ESPN `club.friendly` include le amichevoli principali (tour estivi, trofei) ma non sempre quelle minori: in quei casi lo scheduler non può rilevarle e serve l'avvio manuale.
- **Minuti di recupero dipendenti da ESPN.** Il recupero viene annunciato solo se ESPN pubblica il dato nel commentary. Se la copertura è assente o parziale, il messaggio non viene inviato.
- **Dipendenza dal feed ESPN.** Marcatori, assist e statistiche dipendono dalla copertura di ESPN per quella specifica competizione, che può variare.

-----

<div align="center">

*Progetto amatoriale. Non affiliato a Juventus FC, Telegram, Canva o ESPN.*

</div>
