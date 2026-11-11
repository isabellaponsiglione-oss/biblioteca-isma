import sqlite3
from datetime import datetime
import io
import re
from datetime import date, timedelta
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(page_title='Biblioteca ISMA | Prototipo',page_icon='📚',layout='wide')
st.markdown("""<style>
/* Migliora la leggibilità senza modificare la logica delle schede. */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {font-size: 17px;}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p {font-size: 17px !important;}
[data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] p {font-size: 16px;}
button, input, textarea, [data-baseweb="select"] {font-size: 16px !important;}
[data-testid="stDataFrame"] {font-size: 15px;}
</style>""", unsafe_allow_html=True)
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
        add_cols('readers', {'email':'TEXT','other_contacts':'TEXT','notes':'TEXT','reminders_enabled':'INTEGER NOT NULL DEFAULT 0','first_name':'TEXT','last_name':'TEXT','reader_type':'TEXT'})
        for row in c.execute('SELECT id,name,rank FROM readers WHERE first_name IS NULL AND last_name IS NULL').fetchall():
            parts=(row['name'] or '').strip().split()
            first=parts[0] if parts else ''
            last=' '.join(parts[1:]) if len(parts)>1 else ''
            c.execute('UPDATE readers SET first_name=?,last_name=?,reader_type=? WHERE id=?',(first,last,row['rank'] or '',row['id']))
        add_cols('books', {'section':'TEXT','register_number':'TEXT','sbn_inventory':'TEXT','register_source':'TEXT','copies':'INTEGER NOT NULL DEFAULT 1','notes':'TEXT','classification':'TEXT','work_group':'TEXT','volume_label':'TEXT','withdrawn':'INTEGER NOT NULL DEFAULT 0'})
        add_cols('journals', {'journal_code':'TEXT','subtitle':'TEXT','publisher':'TEXT','place':'TEXT','start_year':'TEXT','end_year':'TEXT','location':'TEXT','notes':'TEXT'})
        add_cols('issues', {'issue_code':'TEXT','volume':'TEXT','pages':'TEXT','location':'TEXT','conservation':'TEXT NOT NULL DEFAULT "Non valutato"','availability':'TEXT NOT NULL DEFAULT "Disponibile"','conservation_notes':'TEXT','notes':'TEXT'})
        add_cols('articles', {'article_code':'TEXT','dewey':'TEXT','notes':'TEXT'})
        for r in c.execute('SELECT id,location,work_group FROM books WHERE work_group IS NULL OR TRIM(work_group)=""').fetchall():
            match=re.fullmatch(r'(.+)-(\d{3})',r['location'] or '')
            if match:c.execute('UPDATE books SET work_group=? WHERE id=?',(match.group(1),r['id']))
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

def clean(value):
    return (value or '').strip().upper()

def conflict(table, field, value, exclude=None):
    if not clean(value):
        return False
    sql=f'SELECT COUNT(*) FROM {table} WHERE UPPER(TRIM(COALESCE({field}, "")))=?'
    args=[clean(value)]
    if exclude is not None:
        sql+=' AND id<>?'
        args.append(exclude)
    with connect() as c:
        return c.execute(sql,args).fetchone()[0]>0

def book_fields(location,section,group):
    loc=clean(location)
    match=re.fullmatch(r'(.+)-(\d{3})',loc)
    if match and not clean(group):group=match.group(1)
    prefix=loc.split('-')[0] if '-' in loc else ''
    if prefix and re.fullmatch(r'[A-Z]+',prefix):
        if clean(section) and clean(section)!=prefix:
            return None,None,'La sezione non corrisponde alla lettera della collocazione.'
        section=prefix
    return section,group,''

def inventory_warning(register_number, sbn_inventory, register_source, group, exclude=None):
    with connect() as c:
        rows=c.execute('SELECT id,register_number,sbn_inventory,register_source,work_group FROM books WHERE id<>?',(exclude or -1,)).fetchall()
    matches=[]
    for r in rows:
        same_group=bool(clean(group)) and clean(group)==clean(r['work_group'])
        if clean(register_number) and clean(register_number)==clean(r['register_number']) and clean(register_source)==clean(r['register_source']) and not same_group:
            matches.append('numero di registro inventariale (nello stesso registro)')
        if clean(sbn_inventory) and clean(sbn_inventory)==clean(r['sbn_inventory']) and not same_group:
            matches.append('inventario SBN')
    return sorted(set(matches))

def next_progressive(table, column, parent_field, parent_id):
    with connect() as c:
        values=[r[0] for r in c.execute(f'SELECT {column} FROM {table} WHERE {parent_field}=?',(parent_id,))]
    nums=[int(str(v).strip()) for v in values if v is not None and re.fullmatch(r'\d+',str(v).strip())]
    return f'{max(nums,default=0)+1:03d}'

def issue_duplicate(journal_id, code, location, exclude=None):
    with connect() as c:
        rows=c.execute('SELECT id,journal_id,issue_code,location FROM issues').fetchall()
    for r in rows:
        if exclude is not None and r['id']==exclude:continue
        if clean(code) and r['journal_id']==journal_id and clean(code)==clean(r['issue_code']):return 'ID fascicolo già presente per questa testata.'
        if clean(location) and clean(location)==clean(r['location']):return 'Collocazione del fascicolo già presente.'
    return ''

def article_duplicate(issue_id, code, exclude=None):
    with connect() as c:
        rows=c.execute('SELECT id,issue_id,article_code FROM articles WHERE issue_id=?',(issue_id,)).fetchall()
    return bool(clean(code) and any(r['id']!=exclude and clean(r['article_code'])==clean(code) for r in rows))

def deletion_ui(table, item_id, label, key, linked=(), soft=False):
    with st.expander('🗑️ Elimina / dismetti la registrazione selezionata'):
        st.warning(f'Operazione riferita a: {label}')
        confirmed=st.checkbox('Confermo di voler procedere',key=f'{key}_confirm')
        if st.button('Conferma eliminazione',disabled=not confirmed,key=f'{key}_delete'):
            with connect() as c:
                for child,foreign in linked:
                    if c.execute(f'SELECT COUNT(*) FROM {child} WHERE {foreign}=?',(item_id,)).fetchone()[0]:
                        st.error('Eliminazione bloccata: esistono registrazioni collegate.');return
                if soft:
                    if c.execute('SELECT COUNT(*) FROM loans WHERE book_id=?',(item_id,)).fetchone()[0]:
                        c.execute('UPDATE books SET withdrawn=1 WHERE id=?',(item_id,))
                        st.success('Volume contrassegnato come dismesso: lo storico dei prestiti resta conservato.')
                        st.rerun()
                c.execute(f'DELETE FROM {table} WHERE id=?',(item_id,))
            st.success('Registrazione eliminata.');st.rerun()

setup()
st.title('📚 Biblioteca ISMA')
st.caption('Versione 0.2.3 • PROTOTIPO DIMOSTRATIVO • Solo dati fittizi • Database locale di prova')
st.warning('Versione dimostrativa: non dispone ancora di autenticazione, database centralizzato persistente o backup automatici esterni. Non inserire dati reali o riservati.',icon='⚠️')
page=st.sidebar.radio('Navigazione',['🏠 Panoramica','📚 Catalogo monografie','📰 Catalogo periodici','🔄 Prestiti','👥 Utenti','📤 Esporta Excel','⚙️ Informazioni'])

if page=='🏠 Panoramica':
    books=fetch('SELECT COUNT(*) n FROM books').iloc[0,0]
    active=fetch('SELECT COUNT(*) n FROM loans WHERE returned_at IS NULL').iloc[0,0]
    late=fetch('SELECT COUNT(*) n FROM loans WHERE returned_at IS NULL AND due_date < ?', (date.today().isoformat(),)).iloc[0,0]
    readers=fetch('SELECT COUNT(*) n FROM readers').iloc[0,0]
    a,b,c,d=st.columns(4)
    a.metric('Volumi',books); b.metric('Prestiti attivi',active); c.metric('Scaduti',late); d.metric('Utenti',readers)
    st.subheader('Prestiti in corso')
    st.dataframe(fetch('''SELECT l.id AS Prestito,b.title AS Titolo,r.name AS Utente,l.loan_date AS Inizio,l.due_date AS Scadenza FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NULL ORDER BY l.due_date'''),hide_index=True,use_container_width=True)

elif page=='📚 Catalogo monografie':
    st.header('Catalogo bibliografico e inventariale')
    st.caption('Collocazione, numero del registro e inventario SBN sono campi distinti. Le copie condividono eventualmente il numero di registro.')
    term=st.text_input('Cerca per titolo, autore, ISBN, soggetto, collocazione, registro o inventario SBN')
    q='''SELECT id, title AS Titolo,author AS Autore,isbn AS ISBN,section AS Sezione,location AS Collocazione,
           register_number AS "N. registro",sbn_inventory AS "Inventario SBN",copies AS Copie,
           (copies-(SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL)) AS Disponibili,
           register_source AS Registro,volume_label AS Volume,withdrawn AS Dismesso FROM books'''
    params=()
    if term.strip():
        cols=['title','author','isbn','subject','location','register_number','sbn_inventory','section','register_source','work_group','volume_label']
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
                section=st.text_input('Sezione disciplinare (es. K)');location=st.text_input('Collocazione (es. G-120 oppure G-120-001)')
                work_group=st.text_input('Codice opera in più volumi (es. G-120)');volume_label=st.text_input('Numero / descrizione volume (es. 001)')
                register_number=st.text_input('N. registro inventario');sbn_inventory=st.text_input('Inventario SBN')
                register_source=st.text_input('Registro di provenienza');copies=st.number_input('Numero copie',1,999,1)
                notes=st.text_area('Note inventariali')
            if st.form_submit_button('Salva scheda'):
                section,work_group,book_error=book_fields(location,section,work_group)
                if book_error:st.error(book_error)
                elif not title.strip():st.error('Il titolo è obbligatorio.')
                elif not location.strip():st.error('La collocazione è obbligatoria.')
                elif conflict('books','location',location):st.error('Collocazione già presente nel catalogo.')
                elif inventory_warning(register_number,sbn_inventory,register_source,work_group):st.error('Identificativo già presente: '+', '.join(inventory_warning(register_number,sbn_inventory,register_source,work_group))+'. Per volumi della stessa opera, indicare lo stesso codice opera in più volumi.')
                else:
                    execute('''INSERT INTO books(title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes,work_group,volume_label)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes,work_group,volume_label))
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
                    work_group=st.text_input('Codice opera in più volumi',row['work_group'] or '');volume_label=st.text_input('Numero / descrizione volume',row['volume_label'] or '')
                    register_number=st.text_input('N. registro',row['register_number'] or '');sbn_inventory=st.text_input('Inventario SBN',row['sbn_inventory'] or '')
                    register_source=st.text_input('Registro di provenienza',row['register_source'] or '');copies=st.number_input('Numero copie',1,999,int(row['copies'] or 1));notes=st.text_area('Note',row['notes'] or '')
                if st.form_submit_button('Aggiorna scheda'):
                    section,work_group,book_error=book_fields(location,section,work_group)
                    active=int(fetch('SELECT COUNT(*) n FROM loans WHERE book_id=? AND returned_at IS NULL',(chosen['id'],)).iloc[0,0])
                    if book_error:st.error(book_error)
                    elif not title.strip():st.error('Titolo obbligatorio.')
                    elif copies<active:st.error(f'Impossibile ridurre le copie sotto i {active} prestiti attivi.')
                    elif not location.strip():st.error('Collocazione obbligatoria.')
                    elif conflict('books','location',location,chosen['id']):st.error('Collocazione già presente nel catalogo.')
                    elif inventory_warning(register_number,sbn_inventory,register_source,work_group,chosen['id']):st.error('Identificativo già presente: '+', '.join(inventory_warning(register_number,sbn_inventory,register_source,work_group,chosen['id'])))
                    else:
                        execute('''UPDATE books SET title=?,author=?,isbn=?,publisher=?,year=?,subject=?,classification=?,section=?,location=?,register_number=?,sbn_inventory=?,register_source=?,copies=?,notes=?,work_group=?,volume_label=? WHERE id=?''',
                                (title,author,isbn,publisher,year,subject,classification,section,location,register_number,sbn_inventory,register_source,copies,notes,work_group,volume_label,chosen['id']))
                        st.success('Scheda aggiornata.');st.rerun()
            deletion_ui('books',chosen['id'],chosen['title'],'book',soft=True)
    st.info('Importazione dai registri Excel, riconciliazione con Access/SBN e gestione fisica individuale delle copie: previste per una fase successiva.')

elif page=='👥 Utenti':
    st.header('Utenti')
    st.dataframe(fetch('''SELECT id,last_name AS Cognome,first_name AS Nome,reader_type AS "Tipologia utente",course AS Corso,office AS Ufficio,phone AS Telefono,email AS Email,other_contacts AS "Altri recapiti",notes AS Note,reminders_enabled AS "Promemoria (predisposti)" FROM readers ORDER BY last_name,first_name'''),hide_index=True,use_container_width=True)
    types=['Frequentatore','Quadro permanente','Personale civile','Altro']
    with st.expander('➕ Nuovo utente'):
        with st.form('new_reader',clear_on_submit=True):
            last=st.text_input('Cognome *');first=st.text_input('Nome *');kind=st.selectbox('Tipologia utente',types);course=st.text_input('Corso');office=st.text_input('Ufficio')
            phone=st.text_input('Telefono');email=st.text_input('Email');other=st.text_input('Altri recapiti');notes=st.text_area('Note');reminders=st.checkbox('Consenti promemoria email (non attivi nella demo)')
            if st.form_submit_button('Salva utente'):
                if first.strip() and last.strip():
                    execute('''INSERT INTO readers(name,first_name,last_name,reader_type,course,office,phone,email,other_contacts,notes,reminders_enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(first.strip()+' '+last.strip(),first.strip(),last.strip(),kind,course,office,phone,email,other,notes,int(reminders)))
                    st.rerun()
                else:st.error('Nome e cognome sono obbligatori.')
    people=options('SELECT id,name,first_name,last_name FROM readers ORDER BY last_name,first_name')
    if people:
        chosen=st.selectbox('Seleziona utente',people,format_func=lambda r:f"{r['last_name'] or ''} {r['first_name'] or ''}".strip())
        with connect() as c:r=dict(c.execute('SELECT * FROM readers WHERE id=?',(chosen['id'],)).fetchone())
        with st.expander('✏️ Modifica utente'):
            with st.form('edit_reader'):
                last=st.text_input('Cognome',r['last_name'] or '');first=st.text_input('Nome',r['first_name'] or '')
                oldkind=r['reader_type'] or 'Altro'
                kind=st.selectbox('Tipologia utente',types+[oldkind] if oldkind not in types else types,index=(types+[oldkind] if oldkind not in types else types).index(oldkind))
                course=st.text_input('Corso',r['course'] or '');office=st.text_input('Ufficio',r['office'] or '')
                phone=st.text_input('Telefono',r['phone'] or '');email=st.text_input('Email',r['email'] or '');other=st.text_input('Altri recapiti',r['other_contacts'] or '');notes=st.text_area('Note',r['notes'] or '');reminders=st.checkbox('Consenti promemoria email (non attivi)',bool(r['reminders_enabled']))
                if st.form_submit_button('Aggiorna utente'):
                    if not first.strip() or not last.strip():st.error('Nome e cognome obbligatori.')
                    else:
                        execute('''UPDATE readers SET name=?,first_name=?,last_name=?,reader_type=?,course=?,office=?,phone=?,email=?,other_contacts=?,notes=?,reminders_enabled=? WHERE id=?''',(first.strip()+' '+last.strip(),first.strip(),last.strip(),kind,course,office,phone,email,other,notes,int(reminders),chosen['id']))
                        st.rerun()
        deletion_ui('readers',chosen['id'],chosen['name'],'reader',linked=[('loans','reader_id')])
        st.subheader('Storico prestiti dell’utente')
        st.dataframe(fetch("SELECT b.title AS Titolo,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi FROM loans l JOIN books b ON b.id=l.book_id WHERE l.reader_id=? ORDER BY l.loan_date DESC",(chosen['id'],)),hide_index=True,use_container_width=True)

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

elif page=='📰 Catalogo periodici':
    st.header('Periodici e spoglio')
    st.caption('Tre livelli collegati: testate → fascicoli → articoli. Dati esclusivamente dimostrativi.')
    t1,t2,t3=st.tabs(['Testate','Fascicoli','Spoglio articoli'])
    with t1:
        st.dataframe(fetch('''SELECT journal_code AS Codice,title AS Titolo,subtitle AS Sottotitolo,publisher AS Editore,place AS Luogo,start_year AS "Anno inizio",end_year AS "Anno fine",issn AS "ISSN / ISBN",location AS Collocazione,notes AS Note FROM journals ORDER BY title'''),hide_index=True,use_container_width=True)
        with st.expander('➕ Nuova testata'):
            with st.form('journal_v02'):
                code=st.text_input('ID periodico (es. RIV-001)');title=st.text_input('Titolo *');subtitle=st.text_input('Sottotitolo');publisher=st.text_input('Editore');place=st.text_input('Luogo');start_year=st.text_input('Anno inizio');end_year=st.text_input('Anno fine');issn=st.text_input('ISSN / ISBN');location=st.text_input('Collocazione');notes=st.text_area('Note')
                if st.form_submit_button('Salva testata'):
                    if not code.strip():st.error('Codice periodico obbligatorio.')
                    elif conflict('journals','journal_code',code):st.error('Codice periodico già presente.')
                    elif title.strip():
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
                        elif not fields['journal_code'].strip():st.error('Codice periodico obbligatorio.')
                        elif conflict('journals','journal_code',fields['journal_code'],chosen['id']):st.error('Codice periodico già presente.')
                        else:
                            execute('UPDATE journals SET '+','.join(f'{col}=?' for col in fields)+' WHERE id=?',tuple(fields.values())+(chosen['id'],));st.rerun()
            deletion_ui('journals',chosen['id'],chosen['title'],'journal',linked=[('issues','journal_id')])
    with t2:
        st.dataframe(fetch('''SELECT i.id,j.journal_code AS "Codice testata",j.title AS Testata,i.issue_code AS "Progressivo",i.year AS Anno,i.volume AS Volume,i.number AS "Numero pubblicato",i.issue_date AS Data,i.pages AS Pagine,i.location AS Collocazione,i.conservation AS Conservazione,i.availability AS Disponibilità,i.conservation_notes AS "Note conservazione",i.notes AS Note FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.location'''),hide_index=True,use_container_width=True)
        journals=options('SELECT id,title,journal_code,location FROM journals ORDER BY title')
        if journals:
            j=st.selectbox('Testata per nuovo fascicolo',journals,format_func=lambda x:f"{x['journal_code'] or 'Senza codice'} · {x['title']}",key='new_issue_journal')
            suggested=next_progressive('issues','issue_code','journal_id',j['id'])
            prefix=(j['journal_code'] or '').strip()
            proposed=f'{prefix}.{suggested}' if prefix else ''
            with st.expander('➕ Nuovo fascicolo'):
                st.caption(f'Progressivo proposto: {suggested} · Collocazione proposta: {proposed or "assegnare prima il codice alla testata"}')
                with st.form('issue_v022'):
                    issue_code=st.text_input('Progressivo inventariale (modificabile)',value=suggested);location=st.text_input('Collocazione (lascia vuoto per generarla automaticamente)',value='')
                    year=st.number_input('Anno',1800,2100,2026);volume=st.text_input('Volume');number=st.text_input('Numero pubblicato (anche 5-6)');issue_date=st.text_input('Data (come riportata nel fascicolo)');pages=st.text_input('Pagine')
                    conservation=st.selectbox('Stato di conservazione',['Non valutato','Ottimo','Buono','Discreto','Deteriorato','Da restaurare']);availability=st.selectbox('Disponibilità',['Disponibile','In prestito','Non consultabile','Mancante']);conservation_notes=st.text_area('Note sulla conservazione');notes=st.text_area('Note generali')
                    if st.form_submit_button('Salva fascicolo'):
                        final_location=location.strip() or (f'{prefix}.{issue_code.strip()}' if prefix else '')
                        err=issue_duplicate(j['id'],issue_code,final_location)
                        if not prefix:st.error('Assegna prima un codice alla testata.')
                        elif not issue_code.strip() or not final_location:st.error('Progressivo e collocazione obbligatori.')
                        elif err:st.error(err)
                        else:
                            execute('''INSERT INTO issues(journal_id,issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(j['id'],issue_code.strip(),year,volume,number,issue_date,pages,final_location,conservation,availability,conservation_notes,notes));st.rerun()
        issues=options('''SELECT i.id,j.title,i.issue_code,i.year,i.number,i.location FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC''')
        if issues:
            selected=st.selectbox('Fascicolo da modificare',issues,format_func=lambda x:f"{x['title']} · {x['location'] or 'senza collocazione'} · {x['year']} / {x['number'] or '—'}",key='issue_choice')
            with connect() as c:r=dict(c.execute('SELECT * FROM issues WHERE id=?',(selected['id'],)).fetchone())
            with st.expander('✏️ Modifica fascicolo selezionato'):
                with st.form('edit_issue_v022'):
                    issue_code=st.text_input('Progressivo inventariale',r['issue_code'] or '');location=st.text_input('Collocazione',r['location'] or '')
                    year=st.number_input('Anno',1800,2100,int(r['year'] or 2026));volume=st.text_input('Volume',r['volume'] or '');number=st.text_input('Numero pubblicato (anche 5-6)',r['number'] or '');issue_date=st.text_input('Data',r['issue_date'] or '');pages=st.text_input('Pagine',r['pages'] or '')
                    cons=['Non valutato','Ottimo','Buono','Discreto','Deteriorato','Da restaurare'];av=['Disponibile','In prestito','Non consultabile','Mancante']
                    conservation=st.selectbox('Conservazione',cons,index=cons.index(r['conservation']) if r['conservation'] in cons else 0);availability=st.selectbox('Disponibilità',av,index=av.index(r['availability']) if r['availability'] in av else 0);conservation_notes=st.text_area('Note conservazione',r['conservation_notes'] or '');notes=st.text_area('Note',r['notes'] or '')
                    if st.form_submit_button('Aggiorna fascicolo'):
                        err=issue_duplicate(r['journal_id'],issue_code,location,selected['id'])
                        if not issue_code.strip() or not location.strip():st.error('Progressivo e collocazione obbligatori.')
                        elif err:st.error(err)
                        else:
                            execute('''UPDATE issues SET issue_code=?,year=?,volume=?,number=?,issue_date=?,pages=?,location=?,conservation=?,availability=?,conservation_notes=?,notes=? WHERE id=?''',(issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes,selected['id']));st.rerun()
            deletion_ui('issues',selected['id'],str(selected['title'])+' / '+str(selected['year']),'issue',linked=[('articles','issue_id')])
    with t3:
        term=st.text_input('Cerca articoli per titolo, autore, parole chiave, Dewey, testata')
        q='''SELECT j.title AS Testata,i.location AS "Collocazione fascicolo",i.year AS Anno,i.number AS "Numero fascicolo",a.article_code AS "Progressivo articolo",a.author AS Autori,a.title AS Articolo,a.pages AS Pagine,a.keywords AS "Parole chiave",a.dewey AS Dewey,a.notes AS Note FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id'''
        params=()
        if term.strip():
            q+=' WHERE '+' OR '.join(f'COALESCE({col},"") LIKE ?' for col in ['a.title','a.author','a.keywords','a.dewey','j.title','i.location'])
            params=tuple('%'+term.strip()+'%' for _ in range(6))
        st.dataframe(fetch(q+' ORDER BY j.title,i.location,a.article_code',params),hide_index=True,use_container_width=True)
        issues=options('''SELECT i.id,j.title,i.location,i.issue_code,i.year,i.number FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.year DESC''')
        if issues:
            issue=st.selectbox('Fascicolo per nuovo articolo',issues,format_func=lambda x:f"{x['title']} · {x['location'] or 'senza collocazione'} · {x['year']} / {x['number'] or '—'}",key='new_article_issue')
            suggested=next_progressive('articles','article_code','issue_id',issue['id'])
            st.caption(f"Codice proposto: {(issue['location'] or 'FASCICOLO')}.{suggested}")
            with st.expander('➕ Nuovo articolo'):
                with st.form('article_v022',clear_on_submit=True):
                    article_code=st.text_input('Progressivo articolo (modificabile)',value=suggested);author=st.text_input('Autori');title=st.text_input('Titolo articolo *');pages=st.text_input('Pagine');keywords=st.text_input('Parole chiave');dewey=st.text_input('Classificazione Dewey');notes=st.text_area('Note')
                    if st.form_submit_button('Salva articolo'):
                        if not title.strip() or not article_code.strip():st.error('Titolo e progressivo obbligatori.')
                        elif article_duplicate(issue['id'],article_code):st.error('Progressivo articolo già presente in questo fascicolo.')
                        else:
                            execute('''INSERT INTO articles(issue_id,article_code,author,title,pages,keywords,dewey,notes) VALUES(?,?,?,?,?,?,?,?)''',(issue['id'],article_code.strip(),author,title,pages,keywords,dewey,notes));st.rerun()
        articles=options('SELECT id,title FROM articles ORDER BY title')
        if articles:
            selected=st.selectbox('Articolo da modificare',articles,format_func=lambda x:x['title'])
            with connect() as c:r=dict(c.execute('SELECT * FROM articles WHERE id=?',(selected['id'],)).fetchone())
            with st.expander('✏️ Modifica articolo selezionato'):
                with st.form('edit_article_v022'):
                    code=st.text_input('Progressivo articolo',r['article_code'] or '');author=st.text_input('Autori',r['author'] or '');title=st.text_input('Titolo',r['title']);pages=st.text_input('Pagine',r['pages'] or '');keywords=st.text_input('Parole chiave',r['keywords'] or '');dewey=st.text_input('Dewey',r['dewey'] or '');notes=st.text_area('Note',r['notes'] or '')
                    if st.form_submit_button('Aggiorna articolo'):
                        if not title.strip() or not code.strip():st.error('Titolo e progressivo obbligatori.')
                        elif article_duplicate(r['issue_id'],code,selected['id']):st.error('Progressivo articolo già presente in questo fascicolo.')
                        else:
                            execute('UPDATE articles SET article_code=?,author=?,title=?,pages=?,keywords=?,dewey=?,notes=? WHERE id=?',(code,author,title,pages,keywords,dewey,notes,selected['id']));st.rerun()
            deletion_ui('articles',selected['id'],selected['title'],'article')

elif page=='📤 Esporta Excel':
    st.header('Esportazione dati in Excel')
    st.caption('Scarica un archivio in formato XLSX. Contiene anche recapiti e note: conservarlo in modo protetto.')
    st.subheader('Riepilogo registrazioni')
    table_names={'Monografie':'books','Testate':'journals','Fascicoli':'issues','Articoli':'articles','Utenti':'readers','Prestiti':'loans'}
    counts={label:int(fetch(f'SELECT COUNT(*) AS n FROM {table}').iloc[0,0]) for label,table in table_names.items()}
    st.dataframe(pd.DataFrame([{'Archivio':k,'Registrazioni attuali':v} for k,v in counts.items()]),hide_index=True,use_container_width=True)
    st.caption('I conteggi si riferiscono al database attualmente aperto da questa istanza della demo.')
    datasets={
      'Monografie':"""SELECT id AS ID,title AS Titolo,author AS Autore,isbn AS ISBN,publisher AS Editore,year AS Anno,subject AS Soggetto,classification AS Classificazione,section AS Sezione,location AS Collocazione,register_number AS "N. registro inventariale",sbn_inventory AS "Inventario SBN",register_source AS "Registro di provenienza",work_group AS "Codice opera multivolume",volume_label AS Volume,copies AS Copie,available AS Disponibili,notes AS Note,withdrawn AS Dismesso FROM books ORDER BY section,location""",
      'Testate':"""SELECT id AS ID,journal_code AS "Codice testata",title AS "Titolo testata",subtitle AS Sottotitolo,publisher AS Editore,place AS Luogo,start_year AS "Anno inizio",end_year AS "Anno fine",issn AS ISSN,location AS Collocazione,notes AS Note FROM journals ORDER BY journal_code""",
      'Fascicoli':"""SELECT i.id AS ID,j.journal_code AS "Codice testata",j.title AS "Titolo testata",i.issue_code AS "Progressivo fascicolo",i.location AS "Collocazione fascicolo",i.year AS Anno,i.volume AS Volume,i.number AS "Numero pubblicato",i.issue_date AS Data,i.pages AS Pagine,i.conservation AS Conservazione,i.availability AS Disponibilità,i.conservation_notes AS "Note conservazione",i.notes AS Note FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.journal_code,i.location""",
      'Articoli':"""SELECT a.id AS ID,j.journal_code AS "Codice testata",j.title AS "Titolo testata",i.location AS "Collocazione fascicolo",i.issue_code AS "Progressivo fascicolo",i.year AS "Anno fascicolo",i.number AS "Numero pubblicato",a.article_code AS "Progressivo articolo",CASE WHEN i.location IS NOT NULL AND TRIM(i.location)<>'' AND a.article_code IS NOT NULL AND TRIM(a.article_code)<>'' THEN i.location||'.'||a.article_code ELSE NULL END AS "Codice articolo completo",a.title AS "Titolo articolo",a.author AS Autori,a.pages AS Pagine,a.keywords AS "Parole chiave",a.dewey AS Dewey,a.notes AS Note FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id ORDER BY j.journal_code,i.location,a.article_code""",
      'Utenti':"""SELECT id AS ID,last_name AS Cognome,first_name AS Nome,reader_type AS "Tipologia utente",course AS Corso,office AS Ufficio,phone AS Telefono,email AS Email,other_contacts AS "Altri recapiti",notes AS Note,reminders_enabled AS "Promemoria predisposti" FROM readers ORDER BY last_name,first_name""",
      'Prestiti':"""SELECT l.id AS ID,b.title AS Titolo,b.location AS Collocazione,r.last_name AS "Cognome utente",r.first_name AS "Nome utente",l.loan_date AS "Data prestito",l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.loan_date DESC""",
    }
    chosen=st.selectbox('Dati da esportare',['Archivio completo']+list(datasets))
    if st.button('Prepara file Excel'):
        from openpyxl.styles import Font,PatternFill,Alignment
        buffer=io.BytesIO()
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            names=datasets if chosen=='Archivio completo' else {chosen:datasets[chosen]}
            for name,sql in names.items():
                frame=fetch(sql)
                for col in frame.columns:
                    if any(t in col.lower() for t in ('isbn','issn','collocazione','inventario','registro','codice','progressivo','telefono')):
                        frame[col]=frame[col].astype('string')
                frame.to_excel(writer,sheet_name=name,index=False)
                ws=writer.sheets[name]
                ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
                for cell in ws[1]:
                    cell.fill=PatternFill('solid',fgColor='17365D');cell.font=Font(color='FFFFFF',bold=True);cell.alignment=Alignment(wrap_text=True,vertical='center')
                ws.row_dimensions[1].height=32
                for cells in ws.columns:
                    letter=cells[0].column_letter
                    ws.column_dimensions[letter].width=min(55,max(16,max(len(str(c.value or '')) for c in list(cells)[:150])+2))
                    if any(t in str(cells[0].value).lower() for t in ('isbn','issn','collocazione','inventario','registro','codice','progressivo','telefono')):
                        for cell in list(cells)[1:]:cell.number_format='@'
        st.download_button('⬇️ Scarica Excel',buffer.getvalue(),file_name='biblioteca_isma_demo_v023.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.info('Questa esportazione non sostituisce il backup tecnico del database.')
    st.subheader('Copia manuale del database dimostrativo')
    st.warning('La copia è soltanto manuale: non è un backup automatico, né garantisce la conservazione dei dati sul server Streamlit.')
    if st.button('Prepara copia SQLite'):
        snapshot=io.BytesIO()
        with connect() as source:
            with sqlite3.connect(':memory:') as target:
                source.backup(target)
                for line in target.iterdump():
                    snapshot.write((line+'\n').encode('utf-8'))
        st.download_button('⬇️ Scarica copia SQL della demo',snapshot.getvalue(),file_name='biblioteca_isma_demo_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.sql',mime='application/sql')
    st.caption('Il file SQL contiene tutte le tabelle e i dati della demo. Non condividerlo pubblicamente.')

else:
    st.header('Informazioni sul prototipo')
    st.write('Versione 0.2.3: demo con caratteri più leggibili, conteggi archivio e copia manuale SQL, oltre alle funzioni della 0.2.2.')
    st.write('Non ancora implementati: autenticazione, database persistente multiutente, backup automatici esterni e verifica di ripristino, importazione Access/Excel/SBN, ricerca ISBN, ruoli e registro operazioni.')
    st.info('Per la versione operativa serviranno verifiche di autorizzazione, sicurezza e trattamento dei dati dell’Amministrazione.')
