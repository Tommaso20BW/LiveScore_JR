# Grafiche GOAL e SAVED Juventus

Il sistema assembla la card in tempo reale usando:

1. uno dei tre background approvati, selezionato dal kit ESPN (`home`, `away`, `third`);
2. PNG scontornato del marcatore;
3. il livello trasparente approvato `overlays/front_goal.png`, davanti al calciatore;
4. la mappa tessile generata della variante, in `word_textures/`, ritagliata
   dentro la sagoma della scritta inferiore;
5. minuto e due piccoli loghi monocromatici delle squadre letti dal live score;
6. nome canonico del giocatore letto da `goal_players.json`.

La scritta GOAL superiore e gia incorporata nei tre background: il codice non
la ridisegna e quindi non puo cambiarne carattere, proporzioni o taglio. I
portieri con la divisa arancione usano automaticamente il background nero.
I loghi italiani locali provengono da FCLogo e vengono colorati come la scritta
GOAL del background. Per un'avversaria non presente nel catalogo locale il bot
usa come ripiego il logo ESPN associato all'ID della partita.

Per un rigore avversario classificato da ESPN come `penalty saved` o
`shootout saved`, il sistema
usa il fondale arancione `backgrounds/saved.png`, il livello trasparente
`overlays/front_saved.png` e il PNG arancione del portiere Juventus. La grafica
SAVED elimina il bordo scuro incorporato nell'overlay, aggiunge un'ombra morbida
alla parola inferiore e colloca il minuto dentro la S superiore. La grafica
non viene mai prodotta per `penalty missed`, né per un rigore della Juventus
parato dal portiere avversario. Se il portiere Juventus non è identificabile
nei partecipanti o nelle formazioni ESPN, rimane il messaggio testuale.

La grafica viene prodotta soltanto se il gol e della Juventus, il marcatore e
nel registro e il PNG possiede vera trasparenza. In ogni altro caso il bot usa
il messaggio testuale esistente.

Per un autogol che assegna il punto alla Juventus il bot non mostra alcun
calciatore: invia soltanto il marcatore con la dicitura `(AUTOGOL)`. Se il nome
del marcatore Juventus non è presente nel registro, applica lo stesso layout
solo-nome ma senza attribuirgli erroneamente la dicitura autogol. Un autogol
commesso dalla Juventus è invece un gol avversario e non produce mai una card
Juventus.

Se ESPN corregge successivamente il marcatore, la card viene rigenerata con il
nuovo giocatore e sostituita nel messaggio Telegram. Sono gestiti anche i due
passaggi opposti: da foto a solo testo per autogol/marcatore assente e da solo
testo a foto quando compare un giocatore registrato.

Un gol su rigore durante la partita mostra `(RIGORE)` accanto al marcatore. I
gol realizzati nella lotteria dei rigori non generano mai una card GOAL: restano
nel messaggio aggregato della serie dal dischetto.

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

L'opzione e disattivata di default, quindi il canale principale conserva il
comportamento attuale finche la grafica non viene approvata.
