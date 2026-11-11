# Biblioteca ISMA — prototipo dimostrativo 0.2.2

Applicazione Streamlit dimostrativa, con dati esclusivamente fittizi.

## Aggiornamenti 0.2.2
- Menu: Panoramica, Catalogo monografie, Catalogo periodici, Prestiti, Utenti, Esporta Excel, Informazioni.
- Utenti: Nome e Cognome distinti, Tipologia utente al posto del Grado. I dati demo preesistenti vengono migrati in modo conservativo (verificare manualmente eventuali nomi composti).
- Monografie: sezione ricavata dalla collocazione; collegamento dei volumi tramite codice dell'opera; condivisione inventariale consentita per volumi collegati.
- Fascicoli: progressivo proposto per ciascuna testata, collocazione derivata automaticamente, numeri pubblicati anche doppi (es. 5-6), controlli su codici e collocazioni duplicate.
- Articoli: progressivo proposto per ciascun fascicolo e controllo duplicati.
- Excel: fogli con intestazioni italiane, dati gerarchici testata/fascicolo/articolo, ordinamento e formato migliorato.
- Prestiti: logica mantenuta dalla 0.2.1.

## Installazione su GitHub
Sostituire i file nella cartella `isma_app/` del repository e confermare con Commit changes. Il file principale resta `isma_app/app.py`.

## Avvertenze
Il database SQLite è locale alla demo e può essere azzerato da un riavvio o ridistribuzione su Streamlit Community Cloud. Questa versione **non** è adatta a dati reali o riservati: non dispone di autenticazione, backup automatici o database multiutente persistente. L'esportazione Excel non sostituisce il backup tecnico.

Non sono ancora implementati: recupero bibliografico via ISBN, importazione massiva dei registri storici, invio email automatiche e hosting operativo protetto.
