import sqlite3
from datetime import date, timedelta
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(page_title='Biblioteca ISMA | Prototipo',page_icon='📚',layout='wide')
DB=Path(__file__).with_name('demo_isma.sqlite3')

def connect():
    c=sqlite3.connect(DB,timeout=10)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c

def setup():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY, isbn TEXT, title TEXT NOT NULL, author TEXT, publisher TEXT, year INTEGER, subject TEXT, location TEXT, inventory TEXT UNIQUE, available INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS readers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, rank TEXT, course TEXT, office TEXT, phone TEXT);
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), reader_id INTEGER NOT NULL REFERENCES readers(id), loan_date TEXT NOT NULL, due_date TEXT NOT NULL, returned_at TEXT, renewals INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS journals(id INTEGER PRIMARY KEY, title TEXT NOT NULL, issn TEXT, subject TEXT);
        CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, journal_id INTEGER NOT NULL REFERENCES journals(id), year INTEGER, number TEXT, issue_date TEXT);
        CREATE TABLE IF NOT EXISTS articles(id INTEGER PRIMARY KEY, issue_id INTEGER NOT NULL REFERENCES issues(id), title TEXT NOT NULL, author TEXT, pages TEXT, keywords TEXT, abstract TEXT);
        ''')
        if not c.execute('SELECT COUNT(*) FROM books').fetchone()[0]:
            c.executemany('INSERT INTO books(isbn,title,author,publisher,year,subject,location,inventory) VALUES(?,?,?,?,?,?,?,?)',[
                ('9780000000001','Leadership nelle organizzazioni','Anna Bianchi','Editore Demo',2022,'Leadership','MAN-001','D-0001'),
                ('9780000000002','Storia del potere aereo','Luca Verdi','Editore Demo',2021,'Storia aeronautica','STO-014','D-0002'),
                ('9780000000003','Comunicazione e complessità','Sara Neri','Editore Demo',2024,'Comunicazione','COM-008','D-0003')])
            c.executemany('INSERT INTO readers(name,rank,course,office,phone) VALUES(?,?,?,?,?)',[
                ('Mario Rossi','Capitano','Corso dimostrativo','Formazione',''),('Giulia Bianchi','Civile','','Biblioteca','')])
            c.execute('INSERT INTO journals(title,issn,subject) VALUES(?,?,?)',('Rivista di studi strategici (demo)','0000-0000','Strategia'))
            j=c.execute('SELECT id FROM journals LIMIT 1').fetchone()[0]
            c.execute('INSERT INTO issues(journal_id,year,number,issue_date) VALUES(?,?,?,?)',(j,2026,'1','2026-01-15'))
            issue=c.execute('SELECT id FROM issues LIMIT 1').fetchone()[0]
            c.execute('INSERT INTO articles(issue_id,title,author,pages,keywords,abstract) VALUES(?,?,?,?,?,?)',(issue,'Leadership e scenari complessi','Paolo Blu','12-21','leadership, complessità','Testo di esempio.'))

def fetch(query,params=()):
    with connect() as c: return pd.read_sql_query(query,c,params=params)

def execute(query,params=()):
    with connect() as c: c.execute(query,params)

def options(query):
    with connect() as c: return [dict(r) for r in c.execute(query)]

setup()
st.title('📚 Biblioteca ISMA')
st.caption('PROTOTIPO DIMOSTRATIVO • Solo dati fittizi • Database locale di prova')
st.warning('Questa versione non è adatta all’uso operativo: non dispone di autenticazione, database multiutente centralizzato o backup automatici. Non inserire dati reali o riservati.',icon='⚠️')
page=st.sidebar.radio('Navigazione',['🏠 Panoramica','📚 Catalogo','🔄 Prestiti','👥 Utenti','📰 Periodici','⚙️ Informazioni'])

if page=='🏠 Panoramica':
    books=fetch('SELECT COUNT(*) n FROM books').iloc[0,0]
    active=fetch('SELECT COUNT(*) n FROM loans WHERE returned_at IS NULL').iloc[0,0]
    late=fetch('SELECT COUNT(*) n FROM loans WHERE returned_at IS NULL AND due_date < ?', (date.today().isoformat(),)).iloc[0,0]
    readers=fetch('SELECT COUNT(*) n FROM readers').iloc[0,0]
    a,b,c,d=st.columns(4)
    a.metric('Volumi',books); b.metric('Prestiti attivi',active); c.metric('Scaduti',late); d.metric('Utenti',readers)
    st.subheader('Prestiti in corso')
    st.dataframe(fetch('''SELECT l.id AS Prestito,b.title AS Titolo,r.name AS Utente,l.loan_date AS Inizio,l.due_date AS Scadenza FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NULL ORDER BY l.due_date'''),hide_index=True,use_container_width=True)

elif page=='📚 Catalogo':
    st.header('Catalogo')
    term=st.text_input('Cerca per titolo, autore, ISBN, soggetto, inventario o collocazione')
    q='SELECT id,isbn,title,author,publisher,year,subject,location,inventory,CASE WHEN available=1 THEN "Disponibile" ELSE "In prestito" END AS stato FROM books'
    params=()
    if term.strip():
        q+=' WHERE '+ ' OR '.join(f'COALESCE({col},"") LIKE ?' for col in ['title','author','isbn','subject','inventory','location'])
        params=tuple('%'+term.strip()+'%' for _ in range(6))
    st.dataframe(fetch(q+' ORDER BY title',params),hide_index=True,use_container_width=True)
    with st.expander('➕ Nuovo volume'):
        with st.form('add_book',clear_on_submit=True):
            isbn=st.text_input('ISBN (facoltativo)')
            title=st.text_input('Titolo *')
            author=st.text_input('Autore')
            publisher=st.text_input('Editore')
            year=st.number_input('Anno',min_value=0,max_value=2100,value=2026)
            subject=st.text_input('Soggetto')
            location=st.text_input('Collocazione')
            inventory=st.text_input('Inventario *')
            if st.form_submit_button('Salva volume'):
                if not title.strip() or not inventory.strip(): st.error('Titolo e inventario sono obbligatori.')
                else:
                    try:
                        execute('INSERT INTO books(isbn,title,author,publisher,year,subject,location,inventory) VALUES(?,?,?,?,?,?,?,?)',(isbn,title,author,publisher,year,subject,location,inventory))
                        st.success('Volume salvato.'); st.rerun()
                    except sqlite3.IntegrityError: st.error('Numero di inventario già presente.')
    with st.expander('✏️ Modifica scheda'):
        books=options('SELECT id,title,inventory FROM books ORDER BY title')
        if books:
            chosen=st.selectbox('Volume da modificare',books,format_func=lambda x:f'{x["title"]} — {x["inventory"]}',key='editbook')
            row=options(f'SELECT * FROM books WHERE id={int(chosen["id"])}')[0]
            with st.form('edit_book'):
                new_title=st.text_input('Titolo',value=row['title'])
                new_author=st.text_input('Autore',value=row['author'] or '')
                new_subject=st.text_input('Soggetto',value=row['subject'] or '')
                new_location=st.text_input('Collocazione',value=row['location'] or '')
                if st.form_submit_button('Aggiorna'):
                    if new_title.strip():
                        execute('UPDATE books SET title=?,author=?,subject=?,location=? WHERE id=?',(new_title,new_author,new_subject,new_location,chosen['id']))
                        st.success('Scheda aggiornata.');st.rerun()
                    else: st.error('Il titolo è obbligatorio.')
    st.info('Ricerca automatica ISBN e sincronizzazione SBN saranno sviluppate nelle prossime versioni.')

elif page=='👥 Utenti':
    st.header('Utenti')
    st.dataframe(fetch('SELECT id,name AS Nominativo,rank AS Grado,course AS Corso,office AS Ufficio FROM readers ORDER BY name'),hide_index=True,use_container_width=True)
    with st.expander('➕ Nuovo utente'):
        with st.form('new_reader',clear_on_submit=True):
            name=st.text_input('Nominativo *'); rank=st.text_input('Grado'); course=st.text_input('Corso'); office=st.text_input('Ufficio')
            if st.form_submit_button('Salva utente'):
                if name.strip():
                    execute('INSERT INTO readers(name,rank,course,office) VALUES(?,?,?,?)',(name,rank,course,office));st.success('Utente salvato.');st.rerun()
                else:st.error('Nominativo obbligatorio.')
    people=options('SELECT id,name FROM readers ORDER BY name')
    if people:
        person=st.selectbox('Consulta lo storico di un utente',people,format_func=lambda r:r['name'])
        st.dataframe(fetch('''SELECT b.title AS Titolo,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi FROM loans l JOIN books b ON b.id=l.book_id WHERE l.reader_id=? ORDER BY l.loan_date DESC''',(person['id'],)),hide_index=True,use_container_width=True)

elif page=='🔄 Prestiti':
    st.header('Prestiti e restituzioni')
    tab1,tab2,tab3=st.tabs(['Nuovo prestito','Prestiti attivi','Storico completo'])
    with tab1:
        available=options('SELECT id,title,inventory FROM books WHERE available=1 ORDER BY title')
        people=options('SELECT id,name FROM readers ORDER BY name')
        if not available or not people:st.info('Servono almeno un libro disponibile e un utente.')
        else:
            with st.form('new_loan'):
                book=st.selectbox('Volume',available,format_func=lambda x:f'{x["title"]} — {x["inventory"]}')
                person=st.selectbox('Utente',people,format_func=lambda x:x['name'])
                start=st.date_input('Data prestito',value=date.today())
                due=st.date_input('Scadenza',value=date.today()+timedelta(days=30))
                if st.form_submit_button('Registra prestito'):
                    if due<start:st.error('La scadenza precede il prestito.')
                    else:
                        with connect() as c:
                            updated=c.execute('UPDATE books SET available=0 WHERE id=? AND available=1',(book['id'],)).rowcount
                            if updated: c.execute('INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)',(book['id'],person['id'],start.isoformat(),due.isoformat()))
                        if updated:st.success('Prestito registrato.');st.rerun()
                        else:st.error('Il volume non è più disponibile.')
    with tab2:
        current=options('''SELECT l.id,b.title,r.name,l.due_date FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NULL ORDER BY l.due_date''')
        if not current:st.info('Nessun prestito attivo.')
        else:
            for loan in current:
                with st.container(border=True):
                    st.write(f'**{loan["title"]}** — {loan["name"]} · scadenza {loan["due_date"]}')
                    a,b=st.columns(2)
                    if a.button('Registra restituzione',key=f'return_{loan["id"]}'):
                        with connect() as c:
                            changed=c.execute('UPDATE loans SET returned_at=? WHERE id=? AND returned_at IS NULL',(date.today().isoformat(),loan['id'])).rowcount
                            if changed:c.execute('UPDATE books SET available=1 WHERE id=(SELECT book_id FROM loans WHERE id=?)',(loan['id'],))
                        st.rerun()
                    if b.button('Rinnova di 30 giorni',key=f'renew_{loan["id"]}'):
                        execute('UPDATE loans SET due_date=date(due_date, "+30 days"),renewals=renewals+1 WHERE id=? AND returned_at IS NULL',(loan['id'],));st.rerun()
    with tab3:
        st.dataframe(fetch('''SELECT l.id,b.title AS Titolo,r.name AS Utente,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi,CASE WHEN l.returned_at IS NULL THEN 'Attivo' ELSE 'Restituito' END AS Stato FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.loan_date DESC'''),hide_index=True,use_container_width=True)
        st.caption('I prestiti restituiti rimangono registrati. In questa demo non è prevista la cancellazione dello storico.')

elif page=='📰 Periodici':
    st.header('Periodici e spoglio')
    t1,t2,t3=st.tabs(['Ricerca articoli','Testate e fascicoli','Nuovo articolo'])
    with t1:
        term=st.text_input('Cerca per titolo articolo, autore, parole chiave o abstract')
        q='''SELECT a.id,a.title AS Articolo,a.author AS Autore,j.title AS Rivista,i.year AS Anno,i.number AS Fascicolo,a.pages AS Pagine,a.keywords AS Parole_chiave FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id'''
        params=()
        if term.strip():
            q+=' WHERE '+ ' OR '.join(f'COALESCE(a.{col},"") LIKE ?' for col in ['title','author','keywords','abstract'])
            params=tuple('%'+term.strip()+'%' for _ in range(4))
        st.dataframe(fetch(q,params),hide_index=True,use_container_width=True)
    with t2:
        st.dataframe(fetch('SELECT * FROM journals'),hide_index=True,use_container_width=True)
        st.dataframe(fetch('SELECT i.id,j.title AS Rivista,i.year AS Anno,i.number AS Numero,i.issue_date AS Data FROM issues i JOIN journals j ON j.id=i.journal_id'),hide_index=True,use_container_width=True)
        with st.expander('➕ Aggiungi testata'):
            with st.form('journal'):
                title=st.text_input('Titolo rivista *');issn=st.text_input('ISSN');subject=st.text_input('Ambito')
                if st.form_submit_button('Salva testata'):
                    if title.strip():execute('INSERT INTO journals(title,issn,subject) VALUES(?,?,?)',(title,issn,subject));st.rerun()
        with st.expander('➕ Aggiungi fascicolo'):
            journals=options('SELECT id,title FROM journals ORDER BY title')
            if journals:
                with st.form('issue'):
                    j=st.selectbox('Testata',journals,format_func=lambda x:x['title'])
                    year=st.number_input('Anno fascicolo',min_value=1800,max_value=2100,value=2026)
                    number=st.text_input('Numero fascicolo');issue_date=st.date_input('Data fascicolo')
                    if st.form_submit_button('Salva fascicolo'):
                        execute('INSERT INTO issues(journal_id,year,number,issue_date) VALUES(?,?,?,?)',(j['id'],year,number,issue_date.isoformat()));st.rerun()
    with t3:
        issues=options('''SELECT i.id,j.title,i.year,i.number FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC''')
        if issues:
            with st.form('article'):
                issue=st.selectbox('Fascicolo',issues,format_func=lambda x:f'{x["title"]} — {x["year"]} / {x["number"]}')
                title=st.text_input('Titolo articolo *');author=st.text_input('Autore articolo')
                pages=st.text_input('Pagine');keywords=st.text_input('Parole chiave');abstract=st.text_area('Abstract')
                if st.form_submit_button('Salva spoglio'):
                    if title.strip():execute('INSERT INTO articles(issue_id,title,author,pages,keywords,abstract) VALUES(?,?,?,?,?,?)',(issue['id'],title,author,pages,keywords,abstract));st.success('Articolo salvato.');st.rerun()
                    else:st.error('Titolo obbligatorio.')

else:
    st.header('Informazioni sul prototipo')
    st.write('Versione 0.1.0: demo locale con SQLite, dati fittizi, catalogo, utenti, prestiti con storico e spoglio periodici.')
    st.write('Non ancora implementati: accesso con credenziali, gestione multiutente in produzione, importazione Access/Excel/SBN, ricerca ISBN automatica, backup, ruoli e registro operazioni.')
    st.info('Per la versione operativa serviranno verifiche di autorizzazione, sicurezza e trattamento dei dati dell’Amministrazione.')
