# Biblioteca ISMA — Prototipo dimostrativo 0.2.1

Applicazione Streamlit per prove **esclusivamente con dati fittizi**. Non usare dati personali, documenti interni o inventari reali: questa versione non dispone di autenticazione, archivio condiviso affidabile, backup automatici o controlli di sicurezza idonei alla produzione.

## Novità 0.2.1
- Catalogo: collocazione obbligatoria e controllo dei duplicati; campi per opere in più volumi (codice opera e numero volume); identificativi inventariali condivisibili tra volumi della stessa opera; modifica ed eliminazione (dismissione se esistono prestiti).
- Periodici: codice testata obbligatorio e non duplicabile in inserimento/modifica; cancellazione con conferma di testate, fascicoli e articoli, impedita se esistono dati collegati.
- Utenti: telefono, email, altri recapiti, note e preferenza per promemoria futuri; modifica ed eliminazione con conferma e protezione dello storico prestiti.
- Esporta Excel: scarica un file XLSX completo con sei fogli (Monografie, Testate, Fascicoli, Articoli, Utenti, Prestiti), oppure una sola sezione.
- Prestiti: logica lasciata invariata rispetto alla versione 0.2.

## Installazione su GitHub / Streamlit
Sostituire `isma_app/app.py`, `isma_app/requirements.txt` e `isma_app/README.md` nel repository esistente. Il file principale resta `isma_app/app.py`. Streamlit Community Cloud ridistribuisce l'app dopo il commit.

## Limiti
I dati sono conservati in SQLite sul filesystem dell'istanza Streamlit: **non sono un archivio permanente** e possono scomparire a un riavvio o ridistribuzione. I dati di prova precedenti potrebbero non sopravvivere all'aggiornamento. L'export Excel è una copia consultabile, non un backup transazionale del database. L'invio email, la ricerca ISBN, l'importazione Excel, la persistenza multiutente e l'autenticazione non sono ancora attivi.
