# Biblioteca ISMA — prototipo dimostrativo v0.2

**Solo dati inventati. Non utilizzare dati reali, personali o istituzionali.**

## Aggiornamenti
- Catalogo: sezione disciplinare, collocazione, numero di registro inventariale, inventario SBN, registro di provenienza, numero copie, note, classificazione. La ricerca distingue i due identificativi inventariali. La disponibilità dei libri è calcolata dai prestiti attivi e dal numero copie.
- Periodici: testate (codice, sottotitolo, editore, luogo, anni, ISSN/ISBN, collocazione, note); fascicoli (codice, volume, numero, data, pagine, collocazione, **conservazione** e **disponibilità** separate, note); spoglio articoli (codice, autore, titolo, pagine, parole chiave, Dewey come testo, note). Modifica delle schede e ricerca.
- Prestiti: stessa interfaccia di v0.1, restituzioni e rinnovi conservati nello storico. Per i libri con più copie il conteggio disponibile è calcolato, ma **non è ancora disponibile la tracciatura del singolo esemplare fisico**.

## Pubblicazione aggiornamento GitHub
Nel repository `biblioteca-isma`, aprire `isma_app/app.py` e scegliere l'icona matita (Edit file). Sostituire **tutto** il contenuto con il file `app.py` di questa versione e confermare `Commit changes`. In alternativa, caricare i file della cartella `isma_app` nel medesimo percorso del repository, sostituendo quelli esistenti. Non creare una nuova cartella annidata.

Streamlit Community Cloud dovrebbe ridistribuire automaticamente l'app dopo il commit. Il file principale resta `isma_app/app.py`. `requirements.txt` è invariato.

## Avvertenze
- Il database SQLite è locale all'istanza Streamlit: può essere cancellato da riavvii o ridistribuzioni. Non è persistente né adatto a uso multiutente operativo.
- I dati inseriti nella versione precedente possono non essere conservati dopo il deployment; eventuali dati demo non sono garantiti.
- Non sono presenti autenticazione, backup centralizzato, importazione dei registri Excel, integrazione SBN, gestione delle copie fisiche, né collegamento automatico dei prestiti ai fascicoli.
- Il campo disponibilità del fascicolo è per ora manuale. L'integrazione con i prestiti dei periodici sarà una fase successiva.
- Per l'uso reale sono necessarie verifiche di autorizzazione, sicurezza e protezione dei dati.
