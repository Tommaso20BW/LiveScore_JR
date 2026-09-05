# Grafiche GOAL e SAVED Juventus

Il sistema assembla la card in tempo reale usando:

1. uno dei tre background approvati, selezionato dal kit ESPN (`home`, `away`, `third`);
2. PNG scontornato del marcatore, quando disponibile;
3. il livello trasparente approvato `overlays/front_goal.png`, davanti al calciatore;
4. la mappa tessile generata della variante, in `word_textures/`, ritagliata
   dentro la sagoma della scritta inferiore;
5. minuto e due piccoli loghi delle squadre letti dal live score;
6. nome canonico del giocatore letto da `goal_players.json`.

La scritta GOAL superiore e gia incorporata nei tre background: il codice non
la ridisegna e quindi non puo cambiarne carattere, proporzioni o taglio. I
portieri con la divisa arancione usano automaticamente il background nero.
I loghi locali provengono da FCLogo e conservano i loro pixel originali, senza
riempimenti o ricolorazioni. A ogni avvio con le grafiche attive il bot controlla
i pacchetti della stagione corrente: sincronizza sempre Serie A e Serie B (cosi
sono comprese anche le possibili avversarie di Coppa Italia) e aggiunge
Champions League, Europa League o Conference League soltanto quando la Juventus
compare nel relativo pacchetto. Scarica nuovamente solo i file mancanti,
corrotti o cambiati.

La cache dinamica e salvata in
`assets/goal_graphics/team_logos/fclogo_cache/` e viene mantenuta tra i run di
GitHub Actions. Se FCLogo e temporaneamente irraggiungibile il live score parte
comunque, usa l'ultima copia valida e, per un logo assente, ripiega sull'immagine
ESPN associata all'ID della squadra.

Per un rigore avversario classificato da ESPN come `penalty saved` o
`shootout saved`, il sistema
usa il fondale arancione `backgrounds/saved.png`, il livello trasparente
`overlays/front_saved.png` e il PNG arancione del portiere Juventus. La grafica
SAVED elimina il bordo scuro incorporato nell'overlay, aggiunge un'ombra morbida
alla parola inferiore e colloca il minuto dentro la S superiore. La grafica
non viene mai prodotta per `penalty missed`, né per un rigore della Juventus
parato dal portiere avversario. Se il portiere Juventus non è identificabile
nei partecipanti o nelle formazioni ESPN, rimane il messaggio testuale.

La grafica viene prodotta per ogni gol assegnato alla Juventus. Se il marcatore
non è nel registro, la card conserva background, GOAL, minuto, loghi e nome,
omettendo soltanto la sagoma del calciatore. Se ESPN non ha ancora comunicato
neppure il nome, viene inviato subito il normale messaggio testuale. Quando il
nome arriva, `editMessageMedia` (Bot API 7.11+) converte quel messaggio nella
card e reinserisce il testo come caption, conservando lo stesso `message_id`:
non viene cancellato o inviato un secondo messaggio. Le caption GOAL restano
entro il limite Telegram di 1024 caratteri.
Nelle amichevoli tutte le grafiche GOAL e SAVED sono disattivate: il bot usa
sempre e soltanto i messaggi testuali esistenti.

Per un autogol che assegna il punto alla Juventus il bot non mostra alcun
calciatore: genera la stessa card con il nome del marcatore e la dicitura
`(AUTOGOL)` direttamente nella grafica. Un autogol commesso dalla Juventus è
invece un gol avversario e non produce mai una card Juventus.

Le didascalie Telegram non vengono cambiate dalla grafica: conservano
esattamente la formattazione storica del bot (`(Autogol)` e `(Rig.)`).

Se ESPN corregge successivamente il marcatore, la card viene rigenerata con il
nuovo giocatore e sostituita nel messaggio Telegram. Se ESPN passa da un
marcatore registrato a un autogol o a un nome senza asset, la vecchia foto viene
sostituita dalla card equivalente senza sagoma.

Un gol su rigore durante la partita mostra `(RIGORE)` accanto al nome dentro la
grafica, senza modificare la didascalia Telegram. I gol realizzati nella
lotteria dei rigori non generano mai una card GOAL: restano nel messaggio
aggregato della serie dal dischetto.

## Dove mettere i giocatori

Le immagini scontornate vanno copiate in:

```text
assets/goal_graphics/players/<slug giocatore>/
```

I nomi esatti sono quelli gia presenti nelle cartelle generate. Non rinominare
i file. `goal_players.json` contiene nomi canonici, alias ESPN e ruolo.

## Preview locale

```powershell
python goal_graphics.py --player "Kenan Yildiz" --kit away --pose arms_crossed --minute 56 --home Juventus --away Inter --home-goals 1 --away-goals 0 --output goal-preview.png

python goal_graphics.py --event saved --player "Guglielmo Vicario" --pose pointing --minute 72 --home Juventus --away Inter --home-goals 1 --away-goals 0 --output saved-preview.png
```

## Preview GitHub senza Telegram

Avvia manualmente il workflow **Test Goal/Saved Graphic**. Il risultato viene fornito
come artifact e non viene pubblicato in alcun canale.

## Test sul Bot JR

Nel workflow **Juventus Live Score - ESPN** seleziona:

- canale: `Bot JR`;
- `goal_graphics`: attivo.

L'opzione e attiva di default anche per gli avvii automatici dello scheduler;
puo essere disabilitata manualmente dal workflow quando serve un run testuale.
