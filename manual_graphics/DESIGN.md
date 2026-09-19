# Generatore manuale Bot JR — specifica

> Documento storico: i requisiti di durata e riavvio qui sotto sono stati
> sostituiti dall'utente. L'implementazione corrente dura **30 minuti**, parte
> **solo manualmente** e non avvia successori. Vedere README.md e PROGRESS.md.

Data: 19 settembre 2026. Base esaminata: main, commit 0c76899.
Stato storico al momento della stesura: progetto da approvare.

## Risultato richiesto

Scrivendo `/grafica` nella chat privata autorizzata del Bot JR, l'utente
compila una richiesta guidata e riceve un file PNG originale. Il servizio
non pubblica sui social, non modifica messaggi precedenti e non cambia i
dati della partita live. Completata una richiesta, resta disponibile per
altre richieste. Ogni processo rimane in ascolto fino a quattro ore e
cede il posto al successivo. I run conclusi precedenti del solo generatore
vengono eliminati; quelli attivi e gli altri workflow non vengono toccati.

## Confini e organizzazione

Tutti i nuovi moduli Python, test e documenti appartengono a
`manual_graphics/`. I nuovi YAML appartengono a `.github/workflows/`.
Si riutilizzano renderer, font, registri giocatori, loghi e texture esistenti:
nessuna copia alternativa delle grafiche e nessuna modifica di layout.

Le sole integrazioni previste nei file esistenti sono:

- `dynamic_kit_runtime.py`: ricezione dei callback kit dal ricevitore comune,
  al posto di getUpdates; la scelta e propagazione del kit restano invariate.
- Collegamento del gestore token Canva comune nel punto di inizializzazione
  del live; non cambiano la scelta della pagina PDF o la composizione.
- Workflow live: configurazione del trasporto condiviso e del gestore Canva.

L'integrazione si attiva insieme al ricevitore dopo aver concluso eventuali
run live della vecchia versione. Non si avvia un secondo lettore Telegram
mentre un vecchio run sta ancora usando getUpdates.

## Procedura Telegram

Solo l'ID utente autorizzato, in chat privata, può avviare e controllare
la procedura. Non basta conoscere il nome del comando o il numero della chat.
Token e credenziali non vengono mai richiesti in chat.

1. `/grafica`: scelta GOAL, SAVED, KICK OFF, HALF TIME, END OF 90', FULL TIME,
   STATS.
2. Selezione competizione e kit home/away/third. I temi UEFA seguono i
   renderer attuali. La Juventus deve essere una delle due squadre.
3. Selezione delle squadre e dell'ordine casa/trasferta dai dati disponibili.
   Nomi ambigui richiedono una scelta; non si inventano loghi o ID.
4. Campi specifici: giocatore e minuto per GOAL; portiere e minuto per SAVED;
   punteggio per le fasi che lo usano; rigori facoltativi nel FULL TIME.
   Il minuto ammette il recupero, ad esempio 90+12.
5. STATS: scelta della fase e immissione dei valori; dati mancanti omessi,
   zero distinto da dato assente, xG facoltativo. Ordine e colori già esistenti.
6. Riepilogo con conferma, possibilità di correggere e `/annulla`.
7. Generazione e invio tramite sendDocument, nome `.png`, senza conversione
   JPEG o ridimensionamento aggiuntivo rispetto al renderer originale.
8. Il servizio torna in ascolto; una richiesta completata non ferma il run.

Le scelte usano pulsanti dove pratico; i valori liberi vengono validati.
Pulsanti di richieste precedenti non possono modificare quella corrente.
Una richiesta inattiva per 30 minuti viene annullata con un avviso.

## Ricezione unica e passaggio al live

Solo il generatore esegue getUpdates per il token condiviso. Il ricevitore
registra gli aggiornamenti prima di confermarli a Telegram, distinguendo:

- messaggi e callback della procedura manuale;
- callback `kit:` destinati al live;
- aggiornamenti non pertinenti, che vengono ignorati senza azioni sul bot.

I callback kit sono accodati in un file di stato separato; il live li legge
e registra il proprio avanzamento in un altro file. Il generatore non scrive
`match_state.json` e il live non riscrive le richieste manuali. Il reset di
fine partita non deve cancellare lo stato del generatore.

Si riutilizza il Gist configurato, con file distinti e un solo autore per file.
Prima dell'attivazione si verifica che il Gist sia privato. Lo stato contiene
soltanto i dati necessari e una coda limitata; non l'intera cronologia chat.
Il live mantiene i controlli evento/chat e la deduplicazione dei callback.

## Render e Canva

Il generatore chiama direttamente i renderer, senza avviare il ciclo partita
e senza usare i metodi di pubblicazione automatica del live. La destinazione
è esclusivamente TELEGRAM_TO_BOT, mai il canale di produzione.

Le fasi Canva richiedono ogni volta un PDF nuovo della pagina 1; non vengono
recuperate le vecchie pagine 2/6/10. Un errore non produce una foto vecchia.

Il refresh OAuth deve avere un unico proprietario: il ricevitore/generatore.
Il live richiede un access token al gestore condiviso, che rinnova soltanto
quando necessario. Lo scambio avviene nello storage privato verificato,
mai in un branch pubblico, nei log o negli artifact. Il token aggiornato
rimane disponibile al successore e il secret GitHub viene mantenuto coerente.
Se il gestore non è disponibile, il live segue il suo normale fallback foto,
senza tentare in parallelo un secondo refresh con un token obsoleto.

La ricezione Telegram prosegue mentre una grafica viene generata. La coda
manuale esegue una generazione alla volta, senza bloccare i pulsanti kit.
Un errore grafico viene comunicato e permette di correggere o riprovare.

## Quattro ore e riavvio

Il budget di ascolto è 14.400 secondi misurati dall'avvio del servizio;
installazione delle dipendenze e chiusura hanno un margine distinto nel job.
Prima della scadenza si salva lo stato e si richiede il successore; il vecchio
processo interrompe il polling prima che il nuovo ne diventi proprietario.
La concurrency dedicata impedisce due ricevitori attivi insieme e non usa
il gruppo del live. Nessun cancel-in-progress che interrompa una generazione.

Una richiesta a metà viene ripresa dal successore. Un render non completato
può essere rigenerato; non si perde il modulo compilato. Se un invio Telegram
ha esito incerto per timeout, non si promette una consegna exactly-once:
si conserva lo stato incerto e si chiede conferma prima di un reinvio.

Errori transitori hanno retry con attesa progressiva. Errori di configurazione
non devono creare centinaia di run: il servizio registra il problema e limita
i riavvii ravvicinati. L'uscita controllata avvia il successore; un controllo
di recupero separato verifica periodicamente i run ed evita dispatch duplicati.
cron-job.org può richiamare quel controllo ogni cinque minuti. Per crash del
runner o indisponibilità GitHub non è garantita ripartenza immediata.

Si prevedono un interruttore persistente di arresto della staffetta e una
modalità di test senza autorilancio, per evitare loop durante lo sviluppo.
La cancellazione della cronologia non modifica minuti consumati o costi.

## Sicurezza e attivazione

Credenziali soltanto nei secret GitHub e nello storage privato necessario.
Permessi minimi: dispatch e pulizia del proprio workflow; accesso al Gist;
Canva attraverso le credenziali già previste. Input Telegram mai interpolati
in comandi shell, percorsi o espressioni del workflow.

Il rollout non attiva automaticamente una staffetta permanente non verificata:
prima test locali, poi un run di prova limitato che invia soltanto al Bot JR,
quindi attivazione continua. Quando un run è attivo, si mostra il singolo job
live nel browser, come richiesto dall'utente.

## Verifica richiesta prima di dichiarare concluso

- Procedura GOAL/SAVED e fasi, recupero minuti, rigori, STATS zero/mancanti.
- Identità non autorizzata e callback vecchi rifiutati.
- Input HTML, nomi ambigui, valori invalidi, immagini/assets mancanti.
- Kit live e procedura manuale contemporanei senza perdere aggiornamenti.
- Cambio run a richiesta incompleta e durante rendering/invio.
- Un solo ricevitore e un solo refresh Canva con live e manuale simultanei.
- Errori Gist/Telegram/Canva/GitHub, retry e assenza di loop di dispatch.
- Pulizia limitata ai run conclusi del proprio workflow.
- Nessun invio al canale pubblico o modifica di messaggi già esistenti.
- Suite esistente del progetto e test nuovi; prova reale del PNG nel Bot JR.

## Esclusioni

Nessuna modifica retroattiva delle foto live, nessuna pubblicazione social,
nessun nuovo stile grafico, nessuna modifica alle decisioni sulla partita.
La disponibilità continua dipende da GitHub e dal controllo di recupero:
la staffetta non equivale a un server con continuità garantita.
