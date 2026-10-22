# LiveScore JR

Bot Telegram per le partite della Juventus (ESPN → Telegram, eseguito da GitHub Actions).

## Comandi rapidi (da CMD / terminale)

```
python -m livescore                 menu interattivo   (su Windows: doppio clic su bot.cmd)
python -m livescore config          parametri regolabili (velocita', attese)
python -m livescore config set poll_seconds 5
python -m livescore team list inter / team set "Inter Milan" Inter Inter / team remove "..."
python -m livescore league list ita / league set ita.1 "🇮🇹"
python -m livescore doctor          controllo generale
python -m livescore test            esegue i test
```
Usati dai workflow: `run`, `keepalive`, `sync-logos`, `schedule-check`, `autodelete`.

## Struttura

| Cartella / file | Contenuto |
|---|---|
| `data/` | Tutto cio' che si modifica senza toccare codice: `settings.json`, `teams.json`, `leagues.json`, `goal_players.json`, `fclogo_manifest.json` |
| `livescore/settings.py` | Segreti (ambiente) e parametri regolabili (`TUNABLES`: una riga per aggiungerne uno) |
| `livescore/constants.py` | Emoji, momenti, mappe eventi ESPN |
| `livescore/core/` | Log, HTTP, testo, nomi squadra, leghe, matching squadre |
| `livescore/espn/` | Client, parser e statistiche ESPN |
| `livescore/telegram/` | Invio/modifica messaggi, auto-delete |
| `livescore/state/` | Stato anti-duplicati su Gist |
| `livescore/match/` | Il ciclo della partita, un file per argomento (`session`, `cycle`, `phases`, `goals`, `substitutions`, `incidents`, `finish`, `stats_job`...) |
| `livescore/graphics/`, `kits/`, `canva/` | Grafiche gol/statistiche, maglie, Canva |
| `livescore/cli.py`, `runner.py`, `scheduler.py` | Comandi, avvio live, controllo scheduler |
| `tests/` | Test e simulatore di partita (`sim_support.py`, `sim_scenarios.py`) |

## Dove metto mano per...

- cambiare un'attesa o la velocita' → `config set ...`
- tradurre una squadra / cambiare un'emoji → `team set` / `league set`
- cambiare il testo dei messaggi → `livescore/match/formatting.py` (e `substitutions.py::render_text` per i cambi)
- un nuovo tipo di evento → un handler in `livescore/match/` e una riga in `session.py`

## Cambi (sostituzioni)

Un messaggio per gruppo di cambi (stessa squadra, stesso tempo, entro ±2'). Se ESPN corregge minuto o giocatori il
messaggio viene modificato; se un cambio si sposta lontano dal gruppo esce dal messaggio e ne riceve uno suo.
Test in `tests/test_substitutions.py`.
