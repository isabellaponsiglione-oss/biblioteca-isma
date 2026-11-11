# Biblioteca ISMA - Prototipo 0.2.3

Versione di collaudo con dati esclusivamente fittizi.

## Novità
- Testi dell'interfaccia leggermente più grandi.
- Riepilogo del numero di registrazioni per archivio nella pagina Esporta Excel.
- Copia manuale SQL del database dimostrativo, ottenuta da uno snapshot SQLite consistente.
- Conservate le funzioni della 0.2.2: cataloghi, prestiti, utenti, numerazioni periodici, export Excel.

## Installazione
Sostituire `app.py`, `requirements.txt` e `README.md` nella cartella `isma_app/` del repository GitHub. Streamlit Cloud ridistribuisce l'applicazione automaticamente.

## Avvertenze di sicurezza
Non utilizzare dati reali o riservati. Questa versione NON include login, database persistente condiviso, backup automatici esterni, cifratura gestita o audit. Lo storage locale di Streamlit Community Cloud non è affidabile come archivio operativo. La copia SQL va scaricata e conservata manualmente in luogo protetto e non rappresenta un sistema di backup verificato per l'uso operativo.

## Passo successivo per uso operativo
Definire una soluzione con database esterno persistente, autenticazione individuale dei tre operatori, autorizzazioni, backup programmati esterni e prove periodiche di ripristino. Prima di inserire dati della biblioteca militare, verificare con i responsabili competenti le regole di trattamento, sicurezza e ospitalità esterna.
