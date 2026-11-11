# Biblioteca ISMA — prototipo 0.1

Questa è una **demo con dati completamente inventati**. Non inserire dati reali della biblioteca o dati personali del personale.

## Cosa funziona
- Catalogo: ricerca, inserimento e modifica di alcuni campi.
- Utenti: inserimento, elenco e storico prestiti.
- Prestiti: registrazione, restituzione senza cancellazione, rinnovo e storico.
- Periodici: testate, fascicoli, spoglio e ricerca articoli.
- Panoramica: contatori e prestiti attivi.

## Come avviare (su computer personale autorizzato)
1. Installa Python 3.11 o successivo, se consentito.
2. Apri il terminale nella cartella del progetto.
3. Esegui `python -m pip install -r requirements.txt`.
4. Esegui `python -m streamlit run app.py`.
5. Apri l'indirizzo locale indicato, di norma `http://localhost:8501`.

Per un utilizzo **senza installazioni sui computer della biblioteca**, il progetto deve essere pubblicato su un hosting approvato. L'hosting non è stato ancora configurato e questo pacchetto non è già online.

## Limiti importanti
- SQLite locale non è il database centralizzato multiutente previsto per la versione operativa.
- Non sono presenti autenticazione, autorizzazioni per ruolo, backup automatici, audit trail o importazione SBN/Access/Excel.
- La funzione ISBN non interroga ancora servizi bibliografici esterni.
- I dati demo sono salvati in `demo_isma.sqlite3`, creato al primo avvio. Per ripartire da zero, con l'app chiusa, elimina quel file.
- Non usare il prototipo per gestire dati reali o riservati.
