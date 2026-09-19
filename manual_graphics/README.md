# Generatore manuale Bot JR

## Avvio (sempre manuale)

1. GitHub → Actions → **Bot JR - Generatore manuale** → **Run workflow** su `main`.
2. Attendi il messaggio «Generatore attivo per 30 minuti» nella chat privata Bot JR.
3. Scrivi `/grafica`, scegli la card e compila le domande. Puoi usare pulsanti
   oppure numeri delle opzioni (a partire da 1).
4. Conferma il riepilogo: ricevi un **file PNG originale**, non una foto compressa.
5. Puoi creare altre immagini fino alla scadenza. Dopo 30 minuti il programma
   termina, restituisce la lettura Telegram al live e pulisce soltanto i vecchi
   run conclusi di questo workflow.

**Nessun avvio automatico, cron, workflow successivo o riavvio dopo errore.**
L'installazione delle dipendenze precede i 30 minuti effettivi di ascolto.
Non avviare più run per estendere la sessione: un secondo avvio manuale resta
in coda per non avere due generatori contemporanei.

## Comandi

- `/grafica`: avvia o riprende la compilazione.
- `/nuova`: ricomincia una compilazione non in generazione.
- `/indietro`: torna alla domanda precedente.
- `/annulla`: chiude la richiesta, non il workflow.
- `/reinvia`: riprova una generazione fallita o un invio incerto **dopo aver
  controllato che il PNG non sia già arrivato**.

GOAL, SAVED, KICK OFF, HALF TIME, END OF 90', FULL TIME e STATS riutilizzano
i renderer correnti. Per le fasi che lo richiedono, viene scaricato un PDF
Canva nuovo della pagina 1. Le statistiche si compilano casa-trasferta;
`-` omette un dato, `0-0` conserva gli zeri, xG è facoltativo.

## Configurazione

Riusa i secret esistenti: TELEGRAM_TOKEN, TELEGRAM_TO_BOT, GH_PAT, GIST_ID,
CANVA_CLIENT_ID, CANVA_CLIENT_SECRET e CANVA_REFRESH_TOKEN. La chat deve essere
**privata**; il suo ID identifica l'utente autorizzato. Il secret facoltativo
MANUAL_GRAPHICS_OWNER_ID consente un controllo aggiuntivo dello stesso ID.

GH_PAT deve poter leggere/scrivere il Gist e aggiornare i secret della repository.
Il Gist deve essere non pubblico; è un Gist «secret», non un deposito cifrato:
non condividere il suo URL. Il token temporaneo GitHub del workflow richiede
contents:write per un lock tecnico e actions:write per la pulizia dei run.

Il branch `jr-manual-canva-lock` contiene **soltanto metadati di lock**, mai
token. Non va cancellato durante un refresh. I token ruotati e lo stato dei
moduli risiedono nei file `manual_*.json` del Gist, separati da match_state.json.
Questo evita che il reset di fine partita cancelli la richiesta manuale.

## Compatibilità con il live

Il live abilitato con MANUAL_GRAPHICS_BRIDGE=1 mantiene la logica delle partite
e le grafiche. Durante il generatore cede la lettura Telegram e riceve i callback
kit dalla coda condivisa. Alla chiusura riprende la lettura diretta. Se il runner
manuale si interrompe brutalmente, il live verifica su GitHub che sia terminato
prima di riprendere. In caso di API non raggiungibile non avvia un secondo lettore.

Prima del primo utilizzo, attendi che finiscano eventuali vecchi run live partiti
prima dell'integrazione. Il generatore aspetta fino a tre minuti la conferma del
live; se manca, termina senza iniziare a leggere Telegram. Non interrompe il live.

Canva usa un token condiviso e un lock durante il rinnovo. Quando il generatore
è spento, il live continua a rinnovarlo autonomamente. Nessun servizio permanente.

## Errori e ripresa

La richiesta compilata rimane nel Gist. Una generazione interrotta può riprendere
al prossimo **avvio manuale**. Per timeout durante l'invio, il sistema conserva
lo stato incerto e non duplica automaticamente il documento. Le richieste ferme
in compilazione per più di 30 minuti scadono.

La pulizia elimina log e artifact dei run conclusi precedenti del generatore;
non elimina i run del live, né il run corrente. Se servono log di un errore,
consultali prima di terminare una nuova esecuzione.

## Test locali (nessun invio Telegram reale)

```text
python -m unittest discover -s manual_graphics/tests -v
python -m unittest discover -s tests -q
```

La specifica iniziale DESIGN.md e il piano PLAN.md descrivono il progetto
storico a quattro ore. Il requisito successivo dell'utente (30 minuti solo
manuali), registrato in PROGRESS.md e implementato qui, li sostituisce.
