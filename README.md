<div align="center">

# ⚡ LiveScore JR

**Bot Telegram che racconta in diretta, evento per evento, le partite della Juventus.**

Gira interamente su **GitHub Actions** — nessun server, nessun database, nessun costo di hosting.

`Python 3.11` · `ESPN API` · `Playwright` · `Canva API` · `GitHub Gist`

</div>

-----

## Cos’è

LiveScore JR monitora automaticamente la partita della Juventus e pubblica su un canale Telegram tutti gli aggiornamenti in tempo reale: calcio d’inizio, gol (con marcatore e assist), sostituzioni, cartellini rossi, rigori sbagliati, gol annullati dal VAR, transizioni di stato (intervallo, supplementari, lotteria dei rigori) e **card statistiche grafiche** a fine primo tempo e a fine partita. Al fischio finale, se in campo c’è la Juve, invia anche una **slide personalizzata** esportata dalla Canva API.

Tutta la logica vive in un unico script Python eseguito da un workflow GitHub Actions: il bot si avvia, trova la partita, la segue fino al triplice fischio e poi si spegne da solo.

-----

## Come funziona

```
                ┌──────────────────────┐
                │   GitHub Actions      │  ← avvio manuale (workflow_dispatch)
                │   main_espn.yml       │
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

1. **Caccia alla partita** — all’avvio il bot scandaglia **304 competizioni** sull’API ESPN finché non trova la gara che coinvolge la Juve, oggi o domani. Le date sono calcolate sul fuso **US Eastern** (quello con cui ESPN indicizza gli eventi), così nemmeno le partite serali americane gli sfuggono.
1. **Battito ogni 6 secondi** — da lì in poi interroga il feed live di ESPN ogni ~6 s e ne ricostruisce lo stato completo: punteggio, eventi, statistiche, persino la maglia in campo.
1. **Notifica** — per ogni novità *reale* invia (o modifica) un messaggio Telegram in italiano.
1. **Persistenza** — dopo ogni cambiamento salva lo stato su un Gist: se il workflow si riavvia a partita in corso, il bot riparte esattamente da dove era.
1. **Spegnimento** — al fischio finale invia statistiche e slide, resetta il Gist e si spegne da solo.

### Motore eventi multi-sorgente

ESPN non serve gli eventi su un piatto solo: li sparpaglia su **quattro feed diversi** — `commentary`, `keyEvents`, `scoringPlays` e `shootout` — spesso ripetendo lo stesso gol o cambio con minuti leggermente diversi e i giocatori in ordine invertito.

Il bot li fonde tutti in **un’unica linea temporale pulita**, abbattendo i doppioni su più livelli: per ID evento, per minuto + giocatore, e per *coppia* di giocatori nei cambi (così “Esce A, entra B” e “Entra B, esce A” diventano un solo cambio). E prima di cantare un gol aspetta 15 secondi e ri-controlla il punteggio: se ESPN “balla”, niente notifiche false.

-----

## Eventi tracciati

|Evento                  |Comportamento                                                                                                                                                                                                                                                                                                                        |
|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**Calcio d’inizio**     |Messaggio all’inizio del primo tempo.                                                                                                                                                                                                                                                                                                |
|**Gol**                 |Notifica immediata al cambio del punteggio (con conferma a 15 s per evitare falsi positivi). Quando ESPN pubblica marcatore e assist, il messaggio viene **modificato via edit** — niente spam. Se la fonte corregge i dati in seguito, il bot aggiorna il messaggio silenziosamente. Gestisce autogol *(Autogol)* e rigori *(Rig.)*.|
|**Gol annullato**       |Se il punteggio cala, attende 120 s di conferma: se l’annullamento è reale invia *GOAL ANNULLATO* e ripulisce lo stato; se era un errore di ESPN, cancella l’eventuale messaggio di annullamento già inviato.                                                                                                                        |
|**Sostituzioni**        |Attende qualche secondo per raggruppare i cambi “gemelli” della stessa squadra nella stessa finestra di minuti in un unico messaggio, aggiornato via edit se ne arrivano altri. Robusto contro i duplicati provenienti da fonti ESPN diverse.                                                                                        |
|**Cartellini rossi**    |Notifica immediata (rosso diretto e doppia ammonizione) con giocatore e minuto.                                                                                                                                                                                                                                                      |
|**Rigori sbagliati**    |Rileva penalty falliti o parati nei tempi regolamentari (esclusa la lotteria finale).                                                                                                                                                                                                                                                |
|**Lotteria dei rigori** |Tracciamento colpo per colpo con sequenza di ✅/❌ per entrambe le squadre.                                                                                                                                                                                                                                                            |
|**Transizioni di stato**|Fine primo tempo, inizio secondo tempo, fine regolamentari, inizio/fine di ciascun tempo supplementare, fine supplementari, rigori, fine partita.                                                                                                                                                                                    |
|**Recupero (catch-up)** |Se il bot parte a partita già in corso con lo stato vuoto, ricostruisce e annuncia i gol già avvenuti prima di passare al rilevamento live.                                                                                                                                                                                          |

-----

## Card statistiche

A **fine primo tempo**, a **fine secondo tempo** (quando si va ai supplementari) e a **fine partita**, il bot genera e invia una card grafica.

Il flusso: il template `stats.html` viene riempito con i dati della gara, renderizzato a **1620×2160 px** da **Playwright/Chromium**, e infine sovrapposto a una texture (`texture_black.png` per i kit chiari home/away, `texture_white.png` per third/default) con **Pillow**.

Le 12 statistiche mostrate sono:

> Possesso palla · Tiri in porta · Tiri totali · Tiri bloccati · Corner · Fuorigioco · Falli · Ammoniti · Espulsi · Parate · Passaggi totali · Precisione passaggi

I valori vengono letti dal box score ESPN della partita, attingendo a più sezioni del feed (`boxscore.teams`, `header.competitions[].competitors`) per coprire qualsiasi competizione.

-----

## Tema maglia dinamico

La grafica della card si adatta al contesto della partita:

|Tema     |Quando si applica                                               |Stile                                                 |
|---------|----------------------------------------------------------------|------------------------------------------------------|
|`home`   |Juventus in casa, in campionato                                 |Bianco/nero a strisce, accenti oro                    |
|`away`   |Juventus in trasferta, in campionato                            |Maglia da trasferta                                   |
|`third`  |Coppe (Champions, Europa, Conference, Coppa Italia, Supercoppa…)|Terza maglia                                          |
|`default`|Partita senza la Juve **o** amichevole                          |Colori reali delle due squadre, ricavati dinamicamente|

Il tema non è cablato a tavolino: il bot legge da ESPN la maglia che la Juve **indossa davvero** in quella specifica partita (`kit_analyzer.py`), così la card riproduce kit e colori reali visti in campo. Per il tema `default` i colori delle due squadre diventano anche i bagliori e i gradienti dello sfondo.

-----

## Slide finale Canva

Al triplice fischio il bot esporta una slide dal design Canva del canale tramite la **Canva REST API** (OAuth) e la allega al messaggio di fine partita.

La slide viene inviata **solo se la Juventus è effettivamente in campo** (controllo sull’ID ESPN `111`). Per i test su altre squadre viene inviato solo il messaggio testuale. Il refresh token OAuth viene **rinnovato e riscritto automaticamente** nei GitHub Secrets a ogni utilizzo, così non scade mai tra una partita e l’altra.

-----

## Architettura

|Componente             |Ruolo                                                                                                                                                                   |
|-----------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**ESPN API**           |Fonte dati. Endpoint pubblici `site.api.espn.com`, **nessuna API key**. `scoreboard` per trovare la partita, `summary` per il live.                                     |
|**GitHub Gist**        |Stato persistente (`match_state.json`): gol rilevati, ID dei messaggi inviati, sostituzioni, cartellini, ecc. Permette al bot di sopravvivere a un riavvio del workflow.|
|**Telegram Bot API**   |Output. Invio, modifica (`editMessageText`) e cancellazione dei messaggi.                                                                                               |
|**Canva API**          |Esportazione della slide finale via OAuth.                                                                                                                              |
|**Playwright + Pillow**|Rendering della card statistiche da HTML a PNG, con overlay texture.                                                                                                    |
|**pynacl**             |Cifratura per aggiornare i GitHub Secrets (rotazione del refresh token Canva).                                                                                          |

-----

## Struttura del repository

```
LiveScore_JR/
├── juve_bot_espn.py             # Logica principale del bot
├── kit_analyzer.py              # Determina kit e colori maglie dai dati ESPN
├── leagues.json                 # 304 competizioni: slug → { emoji, type? }
├── teams.json                   # 677 squadre/nazionali: nome EN → [nome IT, forma breve]
├── stats.html                   # Template HTML della card statistiche
├── texture_black.png            # Overlay texture per i kit home/away
├── texture_white.png            # Overlay texture per i kit third/default
└── .github/workflows/
    ├── main_espn.yml            # Workflow principale (Python 3.11, timeout 240 min)
    └── canva_keep_alive.yml     # Rinnovo del token Canva (Python 3.12)
```

> Le dipendenze non sono in un `requirements.txt`: vengono installate direttamente nei workflow (`requests`, `pillow`, `pynacl`, `playwright` + Chromium).

-----

## Configurazione

### 1. Fork e Secrets

In **Settings → Secrets and variables → Actions** aggiungi:

|Secret               |Descrizione                                                                                                                       |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------|
|`TELEGRAM_TOKEN`     |Token del bot Telegram.                                                                                                           |
|`TELEGRAM_TO`        |Chat ID del canale di destinazione.                                                                                               |
|`GIST_ID`            |ID del Gist usato come stato persistente.                                                                                         |
|`GH_PAT`             |Personal Access Token GitHub (scope `gist` + `repo`). Serve sia per il Gist sia per riscrivere il refresh token Canva nei Secrets.|
|`CANVA_CLIENT_ID`    |Client ID dell’app Canva.                                                                                                         |
|`CANVA_CLIENT_SECRET`|Client Secret dell’app Canva.                                                                                                     |
|`CANVA_REFRESH_TOKEN`|Refresh token OAuth Canva (aggiornato automaticamente a ogni uso).                                                                |

### 2. Crea il Gist di stato

Crea un Gist con un file `match_state.json` contenente `{}` e copia l’ID del Gist nel secret `GIST_ID`.

### 3. (Opzionale) Personalizza design Canva e squadra

Nel codice puoi adattare:

- `CANVA_DESIGN_ID` e `PAGINA_TARGET` — il design e la pagina da esportare come slide finale.
- `JUVE_ID` — l’ID ESPN usato per il branding (logo + tema kit). È volutamente separato da `TEAM_ID`, così una partita senza la Juve resta sul tema `default` con i loghi ESPN.

-----

## Avvio

Il giorno della partita, da **Actions → Juventus Live Score - ESPN → Run workflow**:

- Il bot trova da solo la partita e resta attivo fino al fischio finale (massimo **4 ore**, limite di GitHub Actions).
- Input opzionale **`team_id`** (default `111`, Juventus): permette di testare il bot su un’altra squadra senza toccare il codice. Logo, tema kit e slide Canva restano comunque legati alla Juve.

**Guard di sicurezza** (per non sprecare minuti di GitHub Actions):

- Se il workflow parte a partita **già conclusa** e il Gist è vuoto → si spegne subito senza inviare nulla.
- Se mancano **più di 60 minuti** al calcio d’inizio → termina immediatamente.

**Token Canva:** lancia ogni tanto il workflow **Canva Token Keep-Alive** per rinnovare il refresh token nei periodi senza partite.

-----

## Stack tecnico

`Python 3.11` · `requests` · `Playwright (Chromium)` · `Pillow` · `pynacl` · `GitHub Actions`

**Fonte dati:** ESPN — endpoint pubblici `site.api.espn.com`, nessuna API key. Copertura di **304 competizioni** definite in `leagues.json` (campionati e coppe di tutto il mondo). **Localizzazione italiana** di 677 squadre e nazionali tramite `teams.json`, con forme brevi usate per gli hashtag.

-----

## Limitazioni note

- **Avvio manuale.** Entrambi i workflow sono `workflow_dispatch`: vanno lanciati a mano (non c’è uno scheduler `cron`). Il bot va quindi avviato prima di ogni partita.
- **Finestre “cieche”.** Dopo l’intervallo, la fine dei tempi e il fischio finale il bot attende ~120 s prima di generare le statistiche: in quei brevi intervalli non elabora altri eventi.
- **Dipendenza dal feed ESPN.** Marcatori, assist e statistiche dipendono dalla copertura di ESPN per quella specifica competizione, che può variare.

-----

<div align="center">

*Progetto amatoriale. Non affiliato a Juventus FC, Telegram, Canva o ESPN.*

</div>