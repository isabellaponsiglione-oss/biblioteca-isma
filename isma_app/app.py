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
        # Aggiornamento non distruttivo della struttura della demo 0.1.
        def add_cols(table, definitions):
            existing={r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            for name,kind in definitions.items():
                if name not in existing:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
        add_cols('books', {'section':'TEXT','register_number':'TEXT','sbn_inventory':'TEXT','register_source':'TEXT','copies':'INTEGER NOT NULL DEFAULT 1','notes':'TEXT','classification':'TEXT'})
        add_cols('journals', {'journal_code':'TEXT','subtitle':'TEXT','publisher':'TEXT','place':'TEXT','start_year':'TEXT','end_year':'TEXT','location':'TEXT','notes':'TEXT'})
        add_cols('issues', {'issue_code':'TEXT','volume':'TEXT','pages':'TEXT','location':'TEXT','conservation':'TEXT NOT NULL DEFAULT "Non valutato"','availability':'TEXT NOT NULL DEFAULT "Disponibile"','conservation_notes':'TEXT','notes':'TEXT'})
        add_cols('articles', {'article_code':'TEXT','dewey':'TEXT','notes':'TEXT'})
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
    st.header('Catalogo bibliografico e inventariale')
    st.caption('Collocazione, numero del registro e inventario SBN sono campi distinti. Le copie condividono eventualmente il numero di registro.')
    term=st.text_input('Cerca per titolo, autore, ISBN, soggetto, collocazione, registro o inventario SBN')
    q='''SELECT id, title AS Titolo,author AS Autore,isbn AS ISBN,section AS Sezione,location AS Collocazione,
           register_number AS "N. registro",sbn_inventory AS "Inventario SBN",copies AS Copie,
           (copies-(SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL)) AS Disponibili,
           register_source AS Registro FROM books'''
    params=()
    if term.strip():
        cols=['title','author','isbn','subject','location','register_number','sbn_inventory','section','register_source']
        q+=' WHERE '+' OR '.join(f'COALESCE({col},"") LIKE ?' for col in cols)
        params=tuple('%'+term.strip()+'%' for _ in cols)
    st.dataframe(fetch(q+' ORDER BY title',params),hide_index=True,use_container_width=True)
    with st.expander('➕ Nuova scheda bibliografica / inventariale'):
        with st.form('add_book_v02',clear_on_submit=True):
            a,b=st.columns(2)
            with a:
                title=st.text_input('Titolo *');author=st.text_input('Autore');isbn=st.text_input('ISBN');publisher=st.text_input('Editore');year=st.number_input('Anno edizione',0,2100,2026)
                subject=st.text_input('Soggetto');classification=st.text_input('Classificazione')
            with b:
                section=st.text_input('Sezione disciplinare (es. K)');location=st.text_input('Collocazione (es. K-003)')
                register_number=st.text_input('N. registro inventario');sbn_inventory=st.text_input('Inventario SBN')
                register_source=st.text_input('Registro di provenienza');copies=st.number_input('Numero copie',1,999,1)
                notes=st.text_area('Note inventariali')
            if st.form_submit_button('Salva scheda'):
                if not title.strip():st.error('Il titolo è obbligatorio.')
                else:
                    execute('''INSERT INTO books(title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes))
                    st.success('Scheda salvata.');st.rerun()
    with st.expander('✏️ Modifica scheda'):
        books=options('SELECT id,title,location FROM books ORDER BY title')
        if books:
            chosen=st.selectbox('Seleziona scheda',books,format_func=lambda x:f'{x["title"]} — {x["location"] or "senza collocazione"}')
            with connect() as c: row=dict(c.execute('SELECT * FROM books WHERE id=?',(chosen['id'],)).fetchone())
            with st.form('edit_book_v02'):
                a,b=st.columns(2)
                with a:
                    title=st.text_input('Titolo',row['title']);author=st.text_input('Autore',row['author'] or '');isbn=st.text_input('ISBN',row['isbn'] or '')
                    publisher=st.text_input('Editore',row['publisher'] or '');year=st.number_input('Anno edizione',0,2100,int(row['year'] or 2026));subject=st.text_input('Soggetto',row['subject'] or '');classification=st.text_input('Classificazione',row['classification'] or '')
                with b:
                    section=st.text_input('Sezione',row['section'] or '');location=st.text_input('Collocazione',row['location'] or '')
                    register_number=st.text_input('N. registro',row['register_number'] or '');sbn_inventory=st.text_input('Inventario SBN',row['sbn_inventory'] or '')
                    register_source=st.text_input('Registro di provenienza',row['register_source'] or '');copies=st.number_input('Numero copie',1,999,int(row['copies'] or 1));notes=st.text_area('Note',row['notes'] or '')
                if st.form_submit_button('Aggiorna scheda'):
                    active=int(fetch('SELECT COUNT(*) n FROM loans WHERE book_id=? AND returned_at IS NULL',(chosen['id'],)).iloc[0,0])
                    if not title.strip():st.error('Titolo obbligatorio.')
                    elif copies<active:st.error(f'Impossibile ridurre le copie sotto i {active} prestiti attivi.')
                    else:
                        execute('''UPDATE books SET title=?,author=?,isbn=?,publisher=?,year=?,subject=?,classification=?,section=?,location=?,register_number=?,sbn_inventory=?,register_source=?,copies=?,notes=? WHERE id=?''',
                                (title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes,chosen['id']))
                        st.success('Scheda aggiornata.');st.rerun()
    st.info('Importazione dai registri Excel, riconciliazione con Access/SBN e gestione fisica individuale delle copie: previste per una fase successiva.')

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
        available=options('''SELECT id,title,COALESCE(NULLIF(location,''),inventory) AS inventory FROM books WHERE copies > (SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL) ORDER BY title''')
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
                            updated=c.execute('''SELECT CASE WHEN copies > (SELECT COUNT(*) FROM loans WHERE book_id=? AND returned_at IS NULL) THEN 1 ELSE 0 END FROM books WHERE id=?''',(book['id'],book['id'])).fetchone()[0]
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
                            # La disponibilità è calcolata dai prestiti attivi, senza cancellare lo storico.
                        st.rerun()
                    if b.button('Rinnova di 30 giorni',key=f'renew_{loan["id"]}'):
                        execute('UPDATE loans SET due_date=date(due_date, "+30 days"),renewals=renewals+1 WHERE id=? AND returned_at IS NULL',(loan['id'],));st.rerun()
    with tab3:
        st.dataframe(fetch('''SELECT l.id,b.title AS Titolo,r.name AS Utente,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi,CASE WHEN l.returned_at IS NULL THEN 'Attivo' ELSE 'Restituito' END AS Stato FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.loan_date DESC'''),hide_index=True,use_container_width=True)
        st.caption('I prestiti restituiti rimangono registrati. In questa demo non è prevista la cancellazione dello storico.')

elif page=='📰 Periodici':
    st.header('Periodici e spoglio')
    st.caption('Tre livelli collegati: testate → fascicoli → articoli. Dati esclusivamente dimostrativi.')
    t1,t2,t3=st.tabs(['Testate','Fascicoli','Spoglio articoli'])
    with t1:
        st.dataframe(fetch('''SELECT journal_code AS Codice,title AS Titolo,subtitle AS Sottotitolo,publisher AS Editore,place AS Luogo,start_year AS "Anno inizio",end_year AS "Anno fine",issn AS "ISSN / ISBN",location AS Collocazione,notes AS Note FROM journals ORDER BY title'''),hide_index=True,use_container_width=True)
        with st.expander('➕ Nuova testata'):
            with st.form('journal_v02'):
                code=st.text_input('ID periodico (es. RIV-001)');title=st.text_input('Titolo *');subtitle=st.text_input('Sottotitolo');publisher=st.text_input('Editore');place=st.text_input('Luogo');start_year=st.text_input('Anno inizio');end_year=st.text_input('Anno fine');issn=st.text_input('ISSN / ISBN');location=st.text_input('Collocazione');notes=st.text_area('Note')
                if st.form_submit_button('Salva testata'):
                    if title.strip():
                        execute('''INSERT INTO journals(journal_code,title,subtitle,publisher,place,start_year,end_year,issn,location,notes) VALUES(?,?,?,?,?,?,?,?,?,?)''',(code,title,subtitle,publisher,place,start_year,end_year,issn,location,notes));st.rerun()
                    else:st.error('Titolo obbligatorio.')
        journals=options('SELECT id,title,journal_code FROM journals ORDER BY title')
        if journals:
            chosen=st.selectbox('Modifica testata',journals,format_func=lambda x:f'{x["journal_code"] or "—"} · {x["title"]}',key='edit_journal_choice')
            with connect() as c: r=dict(c.execute('SELECT * FROM journals WHERE id=?',(chosen['id'],)).fetchone())
            with st.expander('✏️ Modifica testata selezionata'):
                with st.form('edit_journal_v02'):
                    fields={}
                    for col,label in [('journal_code','ID periodico'),('title','Titolo'),('subtitle','Sottotitolo'),('publisher','Editore'),('place','Luogo'),('start_year','Anno inizio'),('end_year','Anno fine'),('issn','ISSN / ISBN'),('location','Collocazione'),('notes','Note')]:
                        fields[col]=st.text_input(label,r[col] or '')
                    if st.form_submit_button('Aggiorna testata'):
                        if not fields['title'].strip():st.error('Titolo obbligatorio.')
                        else:
                            execute('UPDATE journals SET '+','.join(f'{col}=?' for col in fields)+' WHERE id=?',tuple(fields.values())+(chosen['id'],));st.rerun()
    with t2:
        st.dataframe(fetch('''SELECT i.id,j.title AS Testata,i.issue_code AS "Codice fascicolo",i.year AS Anno,i.volume AS Volume,i.number AS Numero,i.issue_date AS Data,i.pages AS Pagine,i.location AS Collocazione,i.conservation AS Conservazione,i.availability AS Disponibilità,i.conservation_notes AS "Note conservazione",i.notes AS Note FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC'''),hide_index=True,use_container_width=True)
        journals=options('SELECT id,title,journal_code,location FROM journals ORDER BY title')
        if journals:
            with st.expander('➕ Nuovo fascicolo'):
                with st.form('issue_v02'):
                    j=st.selectbox('Testata',journals,format_func=lambda x:x['title']);issue_code=st.text_input('ID fascicolo (es. 001)');year=st.number_input('Anno',1800,2100,2026);volume=st.text_input('Volume');number=st.text_input('Numero');issue_date=st.text_input('Data (come riportata nel fascicolo)');pages=st.text_input('Pagine');location=st.text_input('Collocazione',value=j['location'] or '')
                    conservation=st.selectbox('Stato di conservazione',['Non valutato','Ottimo','Buono','Discreto','Deteriorato','Da restaurare']);availability=st.selectbox('Disponibilità',['Disponibile','In prestito','Non consultabile','Mancante']);conservation_notes=st.text_area('Note sulla conservazione');notes=st.text_area('Note generali')
                    if st.form_submit_button('Salva fascicolo'):
                        execute('''INSERT INTO issues(journal_id,issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(j['id'],issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes));st.rerun()
        issues=options('SELECT i.id,j.title,i.issue_code,i.year,i.number FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC')
        if issues:
            selected=st.selectbox('Fascicolo da modificare',issues,format_func=lambda x:f'{x["title"]} · {x["year"]} / {x["number"] or "—"}',key='issue_choice')
            with connect() as c:r=dict(c.execute('SELECT * FROM issues WHERE id=?',(selected['id'],)).fetchone())
            with st.expander('✏️ Modifica fascicolo selezionato'):
                with st.form('edit_issue_v02'):
                    issue_code=st.text_input('ID fascicolo',r['issue_code'] or '');year=st.number_input('Anno',1800,2100,int(r['year'] or 2026));volume=st.text_input('Volume',r['volume'] or '');number=st.text_input('Numero',r['number'] or '');issue_date=st.text_input('Data',r['issue_date'] or '');pages=st.text_input('Pagine',r['pages'] or '');location=st.text_input('Collocazione',r['location'] or '')
                    cons=['Non valutato','Ottimo','Buono','Discreto','Deteriorato','Da restaurare'];av=['Disponibile','In prestito','Non consultabile','Mancante']
                    conservation=st.selectbox('Conservazione',cons,index=cons.index(r['conservation']) if r['conservation'] in cons else 0);availability=st.selectbox('Disponibilità',av,index=av.index(r['availability']) if r['availability'] in av else 0);conservation_notes=st.text_area('Note conservazione',r['conservation_notes'] or '');notes=st.text_area('Note',r['notes'] or '')
                    if st.form_submit_button('Aggiorna fascicolo'):
                        execute('''UPDATE issues SET issue_code=?,year=?,volume=?,number=?,issue_date=?,pages=?,location=?,conservation=?,availability=?,conservation_notes=?,notes=? WHERE id=?''',(issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes,selected['id']));st.rerun()
    with t3:
        term=st.text_input('Cerca articoli per titolo, autore, parole chiave, Dewey, testata')
        q='''SELECT j.title AS Testata,i.issue_code AS Fascicolo,i.year AS Anno,a.article_code AS "ID articolo",a.author AS Autori,a.title AS Articolo,a.pages AS Pagine,a.keywords AS "Parole chiave",a.dewey AS Dewey,a.notes AS Note FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id'''
        params=()
        if term.strip():
            q+=' WHERE '+' OR '.join(f'COALESCE({col},"") LIKE ?' for col in ['a.title','a.author','a.keywords','a.dewey','j.title'])
            params=tuple('%'+term.strip()+'%' for _ in range(5))
        st.dataframe(fetch(q+' ORDER BY j.title,i.year,a.article_code',params),hide_index=True,use_container_width=True)
        issues=options('''SELECT i.id,j.title,i.issue_code,i.year,i.number FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC''')
        if issues:
            with st.expander('➕ Nuovo articolo'):
                with st.form('article_v02',clear_on_submit=True):
                    issue=st.selectbox('Fascicolo',issues,format_func=lambda x:f'{x["title"]} · {x["year"]} / {x["number"] or "—"}');article_code=st.text_input('ID articolo (es. 001)');author=st.text_input('Autori');title=st.text_input('Titolo articolo *');pages=st.text_input('Pagine');keywords=st.text_input('Parole chiave');dewey=st.text_input('Classificazione Dewey');notes=st.text_area('Note')
                    if st.form_submit_button('Salva articolo'):
                        if title.strip():
                            execute('''INSERT INTO articles(issue_id,article_code,author,title,pages,keywords,dewey,notes) VALUES(?,?,?,?,?,?,?,?)''',(issue['id'],article_code,author,title,pages,keywords,dewey,notes));st.rerun()
                        else:st.error('Titolo obbligatorio.')
        articles=options('SELECT id,title FROM articles ORDER BY title')
        if articles:
            selected=st.selectbox('Articolo da modificare',articles,format_func=lambda x:x['title'])
            with connect() as c:r=dict(c.execute('SELECT * FROM articles WHERE id=?',(selected['id'],)).fetchone())
            with st.expander('✏️ Modifica articolo selezionato'):
                with st.form('edit_article_v02'):
                    code=st.text_input('ID articolo',r['article_code'] or '');author=st.text_input('Autori',r['author'] or '');title=st.text_input('Titolo',r['title']);pages=st.text_input('Pagine',r['pages'] or '');keywords=st.text_input('Parole chiave',r['keywords'] or '');dewey=st.text_input('Dewey',r['dewey'] or '');notes=st.text_area('Note',r['notes'] or '')
                    if st.form_submit_button('Aggiorna articolo'):
                        if title.strip():
                            execute('UPDATE articles SET article_code=?,author=?,title=?,pages=?,keywords=?,dewey=?,notes=? WHERE id=?',(code,author,title,pages,keywords,dewey,notes,selected['id']));st.rerun()
                        else:st.error('Titolo obbligatorio.')


else:
    st.header('Informazioni sul prototipo')
    st.write('Versione 0.2.0: demo locale con SQLite, dati fittizi, catalogo, utenti, prestiti con storico e spoglio periodici.')
    st.write('Non ancora implementati: accesso con credenziali, gestione multiutente in produzione, importazione Access/Excel/SBN, ricerca ISBN automatica, backup, ruoli e registro operazioni.')
    st.info('Per la versione operativa serviranno verifiche di autorizzazione, sicurezza e trattamento dei dati dell’Amministrazione.')
