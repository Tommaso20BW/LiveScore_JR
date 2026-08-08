<div align="center">

# ⚡ LiveScore JR

**Bot Telegram che segue in diretta le partite della Juventus, evento per evento.**

[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Live score](https://github.com/Tommaso20BW/LiveScore_JR/actions/workflows/main_espn.yml/badge.svg)](https://github.com/Tommaso20BW/LiveScore_JR/actions/workflows/main_espn.yml)
[![Scheduler](https://github.com/Tommaso20BW/LiveScore_JR/actions/workflows/scheduler.yml/badge.svg)](https://github.com/Tommaso20BW/LiveScore_JR/actions/workflows/scheduler.yml)

</div>

## Panoramica

LiveScore JR trova una partita, attende il calcio d'inizio, interroga ESPN durante il live e pubblica su Telegram soltanto gli eventi non ancora notificati.

```text
cron-job.org
      ↓
scheduler.yml → scheduler_check.py
      ↓
main_espn.yml → livescore_runner.py → juve_bot_espn.py
                                      ├─ ESPN: calendario e live
                                      ├─ GitHub Gist: stato
                                      ├─ Telegram: messaggi e card
                                      └─ Canva: immagine finale
```

Non richiede un server sempre acceso. Il workflow principale resta attivo per la durata della gara e termina dopo il risultato finale.

## Ricerca della partita

Il motore principale cerca il `TEAM_ID` configurato nei calendari ESPN di oggi e domani, calcolati nel fuso `America/New_York` usato per indicizzare gli eventi.

- `leagues.json` contiene 323 competizioni controllabili dal bot;
- `teams.json` traduce 678 nomi ESPN in nomi e forme brevi italiane;
- l'ID predefinito è `111`, corrispondente alla Juventus;
- se il kickoff è distante più di 60 minuti, il bot termina e lascia il prossimo tentativo allo scheduler;
- se trova una gara già conclusa con stato ancora vuoto, esce senza inviare messaggi arretrati.

`livescore_runner.py` aggiunge una notifica di servizio nel canale `TELEGRAM_TO_TEST` quando la discovery aggancia una partita. Un errore in questa notifica non blocca il live score.

## Eventi tracciati

ESPN distribuisce gli eventi tra commentary, key events, scoring plays e dati della lotteria. Il bot fonde le fonti in una sola linea temporale e deduplica per ID, minuto, giocatore e coppia entrato/uscito.

| Evento | Comportamento |
| --- | --- |
| Calcio d'inizio e periodi | Primo tempo, intervallo, secondo tempo, supplementari, rigori e fine partita |
| Gol | Conferma il punteggio dopo 15 secondi; aggiunge marcatore, assist, autogol o rigore quando ESPN li espone |
| Gol annullato | Conferma il calo del punteggio per 120 secondi prima di notificare e correggere lo stato |
| Sostituzioni | Raggruppa i cambi della stessa squadra e aggiorna il messaggio quando arrivano eventi gemelli |
| Cartellini rossi | Gestisce rosso diretto e seconda ammonizione |
| Rigori sbagliati | Rileva errore o parata durante la partita, con tolleranza sul minuto |
| Recupero | Legge dal commentary i minuti aggiunti e invia una sola notifica per periodo |
| Lotteria dei rigori | Aggiorna la sequenza di realizzazioni ed errori per entrambe le squadre |

Se il bot riparte a gara in corso, usa il Gist per riprendere gli eventi già gestiti. Con uno stato vuoto ricostruisce i gol precedenti prima di passare al rilevamento live.

## Affidabilità Telegram

- Lo stato di un messaggio viene segnato come inviato soltanto dopo una risposta valida di Telegram.
- I rate limit `429` rispettano `retry_after`.
- Gol e sostituzioni possono essere aggiornati con `editMessageText` invece di generare messaggi duplicati.
- Le notifiche fallite vengono ritentate nei cicli successivi.
- Il polling ordinario del feed avviene ogni circa 6 secondi.

## Stato persistente

Lo stato vive in un Gist con un file `match_state.json`. Contiene, tra l'altro:

- partita e competizione correnti;
- periodi e statistiche già inviati;
- gol e relativi `message_id`;
- sostituzioni, cartellini e rigori sbagliati;
- messaggio della lotteria;
- card statistiche ancora in coda.

La lettura usa tre tentativi. Se il Gist resta irraggiungibile, il bot si ferma per non ripartire da zero e duplicare gli eventi. Al termine della gara lo stato viene riportato a `{}`.

## Card statistiche

A fine primo tempo, a fine regolamentari quando si va ai supplementari e a fine partita, il bot programma una card con due minuti di ritardo. La coda è non bloccante e persistita nel Gist: durante l'attesa il monitoraggio live continua.

La grafica mostra:

- tiri in porta;
- tiri totali;
- calci d'angolo;
- fuorigioco;
- falli;
- ammoniti;
- espulsi;
- parate.

`stats.html` viene renderizzato con Playwright a **1620 × 2160 px** e rifinito con Pillow.

### Tema maglia

`kit_analyzer.py` legge, quando disponibile, `uniform.type` e `uniform.color` dal box score ESPN.

| Tema | Uso | Texture |
| --- | --- | --- |
| `home` | Prima maglia Juventus | `texture_black.png` |
| `away` | Seconda maglia Juventus | `texture_black.png` |
| `third` | Terza maglia Juventus | `texture_gold.png` |
| `default` | Amichevole, altra squadra o dati kit assenti | `texture_white.png` |

Se ESPN non espone la divisa, il codice usa come fallback casa/trasferta nei campionati, third nelle coppe e default nelle amichevoli. I colori delle altre squadre arrivano da `uniform`, poi dai colori del team ESPN e infine da valori di riserva.

## Immagine finale Canva

Al termine di una partita ufficiale della Juventus il bot:

1. rinnova l'access token Canva tramite refresh token;
2. seleziona la pagina del design associata al kit `home`, `away` o `third`;
3. esporta la pagina come PNG;
4. allega l'immagine al messaggio di fine partita.

Per amichevoli o test con un'altra squadra invia soltanto il testo. Se Canva restituisce un nuovo refresh token, il bot prova a riscrivere `CANVA_REFRESH_TOKEN` nei GitHub Secrets; un fallimento viene segnalato nei log e richiede un aggiornamento manuale.

## Scheduler automatico

Il repository non usa il trigger `schedule`. Il flusso previsto è una chiamata esterna a `scheduler.yml` ogni 30 minuti, ad esempio tramite cron-job.org.

`scheduler_check.py` controlla dieci competizioni della Juventus:

- Serie A, Coppa Italia e Supercoppa Italiana;
- Champions League, Europa League, Conference League e Supercoppa UEFA;
- Mondiale per Club, Coppa Intercontinentale e amichevoli.

La finestra di avvio va da 60 minuti prima del kickoff a 140 minuti dopo. La parte successiva al kickoff è un recupero d'emergenza; il bot principale decide poi se la partita è ancora gestibile.

Prima del dispatch il workflow verifica che `main_espn.yml` non sia già in esecuzione o in coda. Un ulteriore gruppo `concurrency` impedisce due live score contemporanei.

### Esempio cron-job.org

Configura una richiesta ogni 30 minuti:

```text
POST https://api.github.com/repos/<utente>/LiveScore_JR/actions/workflows/scheduler.yml/dispatches
Authorization: Bearer <PAT>
Accept: application/vnd.github+json
Content-Type: application/json

{"ref":"main"}
```

Il token esterno deve poter avviare workflow Actions in questo repository.

## Struttura

```text
LiveScore_JR/
├── juve_bot_espn.py
├── livescore_runner.py
├── scheduler_check.py
├── kit_analyzer.py
├── stats.html
├── leagues.json
├── teams.json
├── texture_black.png
├── texture_gold.png
├── texture_white.png
├── requirements.txt
└── .github/workflows/
    ├── main_espn.yml
    ├── scheduler.yml
    └── canva_keep_alive.yml
```

## Requisiti

I workflow usano Python 3.14.

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
playwright install chromium
```

Dipendenze principali: Requests, Playwright, Pillow, PyNaCl e `tzdata`.

## Configurazione

Configura in **Settings → Secrets and variables → Actions**:

| Secret | Uso |
| --- | --- |
| `TELEGRAM_TOKEN` | Token del bot Telegram |
| `TELEGRAM_TO` | Canale principale |
| `TELEGRAM_TO_TEST` | Canale di test e notifica partita trovata |
| `GIST_ID` | ID del Gist contenente `match_state.json` |
| `GH_PAT` | Lettura/scrittura del Gist e aggiornamento del secret Canva |
| `CANVA_CLIENT_ID` | Client ID dell'app Canva |
| `CANVA_CLIENT_SECRET` | Client secret Canva |
| `CANVA_REFRESH_TOKEN` | Refresh token OAuth Canva |

Crea il Gist con un file `match_state.json` inizializzato a `{}`.

## Avvio

### GitHub Actions

Apri **Actions → Juventus Live Score - ESPN → Run workflow** e scegli:

- `team_id`: ID ESPN, default `111`;
- `channel`: `Juventus Reborn` oppure `Test JR`.

### Locale

Imposta almeno le variabili Telegram. Per persistenza e Canva servono anche le credenziali indicate sopra.

```bash
python livescore_runner.py
```

Per rinnovare soltanto il token Canva:

```bash
ONLY_REFRESH_TOKEN=true python juve_bot_espn.py
```

## GitHub Actions

| Workflow | Comportamento |
| --- | --- |
| `main_espn.yml` | Live score manuale o avviato dallo scheduler; timeout 240 minuti |
| `scheduler.yml` | Controllo leggero, anti-doppio avvio e dispatch del live score |
| `canva_keep_alive.yml` | Rinnovo manuale del token Canva senza installare browser e librerie grafiche |

Tutti usano Python 3.14 e sono avviabili con `workflow_dispatch`. Al termine eliminano dalla propria cronologia i run completati.

## Limiti noti

- Gli endpoint ESPN usati sono pubblici ma non documentati e possono cambiare.
- Eventi, minuti e giocatori dipendono dalla velocità e dalla qualità del feed ESPN.
- Il progetto presume un solo live score attivo per volta e un solo file di stato nel Gist.
- Il workflow principale ha un timeout di quattro ore; gare eccezionalmente lunghe richiedono un nuovo run, che riprenderà dal Gist.
- Il rinnovo Canva dipende dalla possibilità del token GitHub di aggiornare i Secrets del repository.
- Il repository non contiene attualmente una suite di test automatizzata.

---

Progetto amatoriale, non affiliato con Juventus Football Club, Telegram, ESPN, GitHub, Canva o cron-job.org.
