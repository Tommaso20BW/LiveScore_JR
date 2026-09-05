# Alias dei loghi GOAL / SAVED

Modifica soltanto `aliases` in `fclogo_cache/manifest.json`.
Usa i **nomi originali ESPN**, non quelli italianizzati di `teams.json`.
Il bot usa i nomi ESPN per i loghi e mantiene le traduzioni nei messaggi.

Esempio nella voce FCLogo esistente (non cambiare slug, file o URL):

```json
"aliases": ["Nijmegen Eendracht Combinatie", "NEC Nijmegen"]
```

Un alias esatto sceglie il logo; se lo stesso alias compare su due club,
nessuno viene scelto. Senza alias esatto resta il confronto prudente dei
nomi. Se non trova un PNG valido, usa ESPN a colori. I loghi locali FCLogo
mantengono la colorazione della grafica.

Il sync non interroga ESPN e non aggiunge automaticamente ID o alias ESPN.
Conserva gli alias manuali negli aggiornamenti e nei riscaricamenti stagionali.
Anche un cambio versione, ad esempio `club-v2025` → `club-v2027`, conserva
gli alias quando nome base e federazione FCLogo coincidono senza ambiguità.
Se FCLogo cambia completamente lo slug o il club esce dal catalogo e rientra
in una stagione successiva, occorre reinserire gli alias nella nuova voce.
Le vecchie voci restano recuperabili dalla cronologia Git.

Salva/committa le modifiche **prima di avviare il workflow**. Actions ripristina
dalla cache solo i PNG: il manifest modificabile proviene sempre dal repository.
Non servono `team_logos.json`, registri ID separati o elenchi ESPN scaricati.
