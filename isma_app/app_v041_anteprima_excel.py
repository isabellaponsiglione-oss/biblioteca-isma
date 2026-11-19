import psycopg
from psycopg.rows import dict_row
import requests
from datetime import datetime
import io
import re
from datetime import date, timedelta
from urllib.parse import quote
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
# Credenziali solo nei Secrets Streamlit, mai nel repository.
required = ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'DATABASE_URL', 'OPERATOR_EMAILS')
if any(k not in st.secrets for k in required):
    st.error('Configurazione incompleta. Occorrono SUPABASE_URL, SUPABASE_ANON_KEY, DATABASE_URL e OPERATOR_EMAILS nei Secrets di questa applicazione.')
    st.stop()

base = str(st.secrets['SUPABASE_URL']).rstrip('/')
api_key = str(st.secrets['SUPABASE_ANON_KEY'])
headers = {'apikey': api_key, 'Content-Type': 'application/json'}
allowed = {str(x).strip().casefold() for x in st.secrets['OPERATOR_EMAILS']}
if not allowed:
    st.error('Elenco operatori autorizzati vuoto.')
    st.stop()

def current_user(token):
    try:
        r = requests.get(base + '/auth/v1/user', headers={**headers, 'Authorization': 'Bearer ' + token}, timeout=10)
        if r.ok:
            return r.json()
    except requests.RequestException:
        pass
    return None

if 'access_token' not in st.session_state:
    st.session_state.access_token = None
user = current_user(st.session_state.access_token) if st.session_state.access_token else None
if not user or str(user.get('email', '')).strip().casefold() not in allowed:
    st.session_state.access_token = None
    st.title('📚 Biblioteca ISMA — Accesso operatori')
    with st.form('operator_login'):
        email = st.text_input('Email operatore').strip()
        password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Accedi')
    if submitted:
        try:
            r = requests.post(base + '/auth/v1/token?grant_type=password', headers=headers,
                              json={'email': email, 'password': password}, timeout=12)
            payload = r.json()
            token = payload.get('access_token') if r.ok else None
            verified = current_user(token) if token else None
            if verified and str(verified.get('email', '')).strip().casefold() in allowed:
                st.session_state.access_token = token
                st.rerun()
            else:
                st.error('Accesso non autorizzato o credenziali non valide.')
        except (requests.RequestException, ValueError):
            st.error('Autenticazione temporaneamente non disponibile.')
    st.stop()

with st.sidebar:
    st.caption('Operatore: ' + str(user.get('email', '')))
    if st.button('Esci'):
        st.session_state.access_token = None
        st.rerun()

# Compatibilita' con la logica della demo: connessione PostgreSQL a ogni operazione.
# Nessun dato bibliografico viene creato automaticamente.
class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
    @property
    def rowcount(self):
        return self.cursor.rowcount
    def fetchone(self):
        r = self.cursor.fetchone()
        return Row(r) if r is not None else None
    def fetchall(self):
        return [Row(r) for r in self.cursor.fetchall()]
    def __iter__(self):
        for r in self.cursor:
            yield Row(r)

class Connection:
    def __init__(self):
        self.conn = psycopg.connect(str(st.secrets['DATABASE_URL']), connect_timeout=10,
                                    sslmode='require', row_factory=dict_row)
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self.conn.rollback()
            else:
                self.conn.commit()
        finally:
            self.conn.close()
    def execute(self, sql, params=()):
        # La sintassi della demo SQLite usava ? e alcune stringhe fra doppi apici.
        sql = sql.replace('?', '%s')
        sql = sql.replace('""', "''")
        sql = sql.replace('date(due_date, "+30 days")', "(due_date::date + INTERVAL '30 days')::text")
        return Cursor(self.conn.execute(sql, params))

def connect():
    return Connection()

def fetch(query, params=()):
    with connect() as c:
        return _fetch_frame(c, query, params)

def _fetch_frame(c, query, params):
    cur = c.execute(query, params)
    rows = cur.fetchall()
    names = [d.name for d in cur.cursor.description]
    return pd.DataFrame([dict(r) for r in rows], columns=names)

def execute(query, params=()):
    with connect() as c:
        c.execute(query, params)

def options(query, params=()):
    with connect() as c:
        return [dict(r) for r in c.execute(query, params)]

def build_labels_pdf(records, width_mm=45, height_mm=22, columns=4, rows=11,
                     left_mm=12, top_mm=12, gap_x_mm=2, gap_y_mm=2, label_type='Dorso'):
    """Produce A4 printable labels without changing the database."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    output=io.BytesIO()
    pdf=canvas.Canvas(output,pagesize=A4)
    page_w,page_h=A4
    w,h=width_mm*mm,height_mm*mm
    if (left_mm+columns*width_mm+(columns-1)*gap_x_mm)*mm > page_w or (top_mm+rows*height_mm+(rows-1)*gap_y_mm)*mm > page_h:
        raise ValueError('Le etichette non entrano nel foglio A4. Riduci dimensioni, margini o spazi.')
    for idx,rec in enumerate(records):
        if idx and idx%(columns*rows)==0:pdf.showPage()
        pos=idx%(columns*rows)
        col=pos%columns; row=pos//columns
        x=(left_mm+col*(width_mm+gap_x_mm))*mm
        y=page_h-(top_mm+row*(height_mm+gap_y_mm))*mm-h
        location=str(rec.get('location') or '').strip()
        title=str(rec.get('title') or '').strip()
        inventory=str(rec.get('register_number') or '').strip()
        pdf.setFillColorRGB(0.08,0.14,0.22)
        pdf.setFont('Helvetica-Bold', min(15,max(8,width_mm/3.6)))
        pdf.drawCentredString(x+w/2,y+h*.56,location[:28])
        if label_type=='Inventario':
            pdf.setFont('Helvetica',7)
            pdf.drawCentredString(x+w/2,y+h*.27,('Inv. '+inventory)[:38])
        elif label_type=='Fascicolo':
            pdf.setFont('Helvetica',7)
            pdf.drawCentredString(x+w/2,y+h*.27,title[:35])
    pdf.save();output.seek(0)
    return output.getvalue()

def lookup_isbn(raw):
    """Recupero facoltativo da Open Library; non modifica il database."""
    isbn=re.sub(r'[^0-9Xx]','',raw or '').upper()
    if len(isbn) not in (10,13) or not re.fullmatch(r'[0-9]{9}[0-9X]|[0-9]{13}',isbn):
        raise ValueError('ISBN non valido')
    r=requests.get('https://openlibrary.org/isbn/'+quote(isbn)+'.json',timeout=10)
    if r.status_code==404:return None
    r.raise_for_status()
    data=r.json()
    authors=[]
    for item in data.get('authors',[])[:5]:
        key=item.get('key','')
        if not key.startswith('/authors/'):continue
        try:
            ar=requests.get('https://openlibrary.org'+key+'.json',timeout=5)
            if ar.ok:authors.append(ar.json().get('name',''))
        except requests.RequestException:pass
    publishers=data.get('publishers') or []
    year_match=re.search(r'\b(1[5-9]\d{2}|20\d{2})\b',str(data.get('publish_date','')))
    return {'title':data.get('title',''),'author':', '.join(filter(None,authors)),
            'publisher':publishers[0] if publishers else '',
            'year':int(year_match.group(0)) if year_match else 2026,'isbn':isbn}

def clean(value):
    return (value or '').strip().upper()

def conflict(table, field, value, exclude=None):
    if not clean(value):
        return False
    sql=f"SELECT COUNT(*) FROM {table} WHERE UPPER(TRIM(COALESCE({field}, '')))=?"
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
    matches=[]
    with connect() as c:
        if clean(register_number):
            r=c.execute("""SELECT 1 FROM books WHERE UPPER(TRIM(COALESCE(register_number,'')))=?
                AND UPPER(TRIM(COALESCE(register_source,'')))=? AND id<>?
                AND (?='' OR UPPER(TRIM(COALESCE(work_group,'')))<>?) LIMIT 1""",
                (clean(register_number),clean(register_source),exclude or -1,clean(group),clean(group))).fetchone()
            if r: matches.append('numero di registro inventariale (nello stesso registro)')
        if clean(sbn_inventory):
            r=c.execute("""SELECT 1 FROM books WHERE UPPER(TRIM(COALESCE(sbn_inventory,'')))=?
                AND id<>? AND (?='' OR UPPER(TRIM(COALESCE(work_group,'')))<>?) LIMIT 1""",
                (clean(sbn_inventory),exclude or -1,clean(group),clean(group))).fetchone()
            if r: matches.append('inventario SBN')
    return matches

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

def notify_success(message):
    """Show a confirmation after the next Streamlit rerun."""
    st.session_state['isma_success_message'] = message
    st.rerun()

def deletion_ui(table, item_id, label, key, linked=(), soft=False):
    with st.expander('🗑️ Elimina / dismetti la registrazione selezionata'):
        st.warning(f'Operazione riferita a: {label}')
        confirmed=st.checkbox('Confermo di voler procedere',key=f'{key}_confirm')
        if st.button('Conferma eliminazione',disabled=not confirmed,key=f'{key}_delete'):
            blocked=False
            dismesso=False
            with connect() as c:
                for child,foreign in linked:
                    if c.execute(f'SELECT COUNT(*) FROM {child} WHERE {foreign}=?',(item_id,)).fetchone()[0]:
                        blocked=True
                        break
                if not blocked:
                    if soft and c.execute('SELECT COUNT(*) FROM loans WHERE book_id=?',(item_id,)).fetchone()[0]:
                        c.execute('UPDATE books SET withdrawn=1 WHERE id=?',(item_id,))
                        dismesso=True
                    else:
                        c.execute(f'DELETE FROM {table} WHERE id=?',(item_id,))
            if blocked:
                st.error('Eliminazione bloccata: esistono registrazioni collegate.')
            elif dismesso:
                notify_success('Volume dismesso correttamente. Lo storico dei prestiti è conservato.')
            else:
                notify_success('Registrazione eliminata correttamente.')

st.title('📚 Biblioteca ISMA')
st.caption('Versione 0.4.1 • COLLAUDO • Database Supabase condiviso • Solo dati fittizi')
st.warning('Versione di collaudo: autenticazione e database condiviso attivi, ma sicurezza, backup e concorrenza ancora da validare. Non inserire dati reali o riservati.',icon='⚠️')
page=st.sidebar.radio('Navigazione',['🏠 Panoramica','📚 Catalogo monografie','📰 Catalogo periodici','🔄 Prestiti','👥 Utenti','🏷️ Etichette','📥 Anteprima inventari','📤 Esporta Excel','⚙️ Informazioni'])
if st.session_state.get('isma_success_message'):
    st.success(st.session_state.pop('isma_success_message'), icon='✅')

def _excel_text(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()

def _register_rows(file_obj):
    """Lettura senza scrittura: solo fogli REG., con due strutture note della lettera A."""
    from openpyxl import load_workbook
    wb=load_workbook(file_obj,read_only=True,data_only=True)
    records=[]; skipped=[]; used=[]
    try:
        for sheet in wb:
            name=sheet.title.strip()
            if not re.match(r'^REG\s*\.',name,re.I) or 'SCARICO' in name.upper():
                skipped.append(name);continue
            used.append(name)
            sheet.reset_dimensions()
            iterator=sheet.iter_rows(values_only=True)
            header=next(iterator,())
            header_cells=[_excel_text(x).upper() for x in header]
            offset=1 if any('REGISTRO INVENTARIO' in x for x in header_cells[2:3]) else 0
            # REG.N.1: due colonne preliminari; REG. N. A VARIE: una.
            # I campi sono allineati usando l'intestazione, non la posizione assoluta.
            idx_reg=next((i for i,x in enumerate(header_cells) if 'REGISTRO INVENTARIO' in x),None)
            idx_sbn=next((i for i,x in enumerate(header_cells) if 'INVENTARIO SBN' in x),None)
            idx_author=next((i for i,x in enumerate(header_cells) if x=='AUTORE'),None)
            idx_title=next((i for i,x in enumerate(header_cells) if x=='TITOLO'),None)
            idx_qty=next((i for i,x in enumerate(header_cells) if 'Q.TA' in x or 'Q.TÀ' in x),None)
            idx_pub=next((i for i,x in enumerate(header_cells) if x.startswith('EDITORE')),None)
            idx_year=next((i for i,x in enumerate(header_cells) if x.startswith('ANNO ED')),None)
            idx_loc=next((i for i,x in enumerate(header_cells) if 'COLLOCAZIONE' in x),None)
            idx_pages=next((i for i,x in enumerate(header_cells) if x=='PAGINE'),None)
            idx_price=next((i for i,x in enumerate(header_cells) if x.startswith('PREZZO')),None)
            idx_isbn=next((i for i,x in enumerate(header_cells) if 'ISBN' in x),None)
            idx_notes=next((i for i,x in enumerate(header_cells) if x=='NOTE'),None)
            if idx_title is None or idx_loc is None or idx_reg is None:
                skipped.append(name+' (intestazioni non riconosciute)');used.pop();continue
            def val(row,i):return _excel_text(row[i]) if i is not None and i<len(row) else ''
            for line,row in enumerate(iterator,2):
                title=val(row,idx_title)
                if not title:continue
                letter=val(row,idx_loc).upper()
                number=val(row,idx_loc+1)
                if re.fullmatch(r'\d+',number):
                    number=number.zfill(3)
                location=f'{letter}-{number}' if letter and number else ''
                warnings=[]
                if not location:warnings.append('Collocazione incompleta')
                if not re.fullmatch(r'[A-Z]+-\d{3}(?:-\d{3})?',location):
                    warnings.append('Formato collocazione da verificare')
                year_raw=val(row,idx_year)
                year=int(year_raw) if re.fullmatch(r'\d{4}',year_raw) and 1500<=int(year_raw)<=2100 else None
                if year_raw and year is None:warnings.append('Anno non riconosciuto')
                quantity=val(row,idx_qty)
                copies=int(quantity) if re.fullmatch(r'\d+',quantity) and int(quantity)>0 else 1
                if quantity and str(copies)!=quantity:warnings.append('Quantità da verificare')
                notes=val(row,idx_notes)
                details='; '.join(filter(None,[f'Pagine: {val(row,idx_pages)}' if val(row,idx_pages) else '',f'Prezzo storico: {val(row,idx_price)}' if val(row,idx_price) else '',notes]))
                records.append({'Foglio':name,'Riga':line,'Collocazione':location,'Titolo':title,'Autore':val(row,idx_author),'Editore':val(row,idx_pub),'Anno':year,'ISBN':val(row,idx_isbn),'N. registro':val(row,idx_reg),'Inventario SBN':val(row,idx_sbn),'Copie':copies,'Note':details,'Anomalie':'; '.join(warnings)})
    finally:
        wb.close()
    seen={}
    for rec in records:
        loc=rec['Collocazione']
        if loc:
            if loc in seen:
                rec['Anomalie']+='; Collocazione ripetuta nel file'
                seen[loc]['Anomalie']+='; Collocazione ripetuta nel file'
            else:seen[loc]=rec
    return records,used,skipped

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
    term=st.text_input('Cerca per titolo, autore, ISBN, soggetto, collocazione, registro o inventario SBN', key='book_search')
    st.caption('Per velocizzare il catalogo vengono mostrate al massimo 50 schede alla volta. Digita almeno 2 caratteri per cercare.')
    cols=['title','author','isbn','subject','location','register_number','sbn_inventory','section','register_source','work_group','volume_label','classification']
    if len(term.strip()) >= 2:
        where=' OR '.join(f"COALESCE({col}, '') ILIKE ?" for col in cols)
        params=tuple('%'+term.strip()+'%' for _ in cols)
        q=f'''SELECT id, title AS Titolo, author AS Autore, isbn AS ISBN, location AS Collocazione,
                register_number AS "N. registro", sbn_inventory AS "Inventario SBN", copies AS Copie,
                copies-(SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL) AS Disponibili,
                withdrawn AS Dismesso FROM books WHERE ({where}) ORDER BY title LIMIT 50'''
        results=fetch(q,params)
        st.dataframe(results,hide_index=True,use_container_width=True)
        if len(results)==50:st.info('Visualizzati i primi 50 risultati: affina la ricerca per individuare la scheda.')
    elif term.strip():
        st.info('Inserisci almeno due caratteri.')
    else:
        st.info('Inserisci un termine per cercare nel catalogo. Nessun caricamento completo automatico.')
    with st.expander('➕ Nuova scheda bibliografica / inventariale'):
        isbn_lookup=st.text_input('ISBN da cercare',key='isbn_lookup_v040',help='Inserisci ISBN-10 o ISBN-13 e premi il pulsante.')
        if st.button('🔎 Cerca dati bibliografici',key='lookup_isbn_v040'):
            try:
                found=lookup_isbn(isbn_lookup)
                if found:
                    st.session_state['isbn_prefill_v040']=found
                    st.success('Dati trovati. Verificali e completa i campi prima di salvare.')
                else:
                    st.session_state.pop('isbn_prefill_v040', None)
                    st.warning('Nessun dato trovato. Puoi compilare la scheda manualmente.')
            except (requests.RequestException, ValueError) as exc:
                st.error('Ricerca ISBN non riuscita: verifica il codice o riprova. Puoi inserire i dati manualmente.')
        prefill=st.session_state.get('isbn_prefill_v040',{})
        with st.form('add_book_v02',clear_on_submit=True):
            a,b=st.columns(2)
            with a:
                title=st.text_input('Titolo *',value=prefill.get('title',''));author=st.text_input('Autore',value=prefill.get('author',''));isbn=st.text_input('ISBN',value=prefill.get('isbn',''));publisher=st.text_input('Editore',value=prefill.get('publisher',''));year=st.number_input('Anno edizione',0,2100,int(prefill.get('year') or 2026))
                subject=st.text_input('Soggetto');classification=st.text_input('Classificazione Decimale Dewey (CDD)')
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
                    st.session_state.pop('isbn_prefill_v040',None)
                    notify_success('Scheda bibliografica salvata correttamente.')
    with st.expander('📖 Consulta Dewey (orientamento per classi principali)'):
        st.caption('Ricerca per numero o argomento sulle 10 classi principali. Non è una consultazione completa delle tavole Dewey: per la classificazione dettagliata occorre una fonte autorizzata.')
        dewey_classes=[('000','Generalità, informatica e informazione'),('100','Filosofia e psicologia'),('200','Religione'),('300','Scienze sociali'),('400','Linguaggio'),('500','Scienze naturali e matematica'),('600','Tecnologia e scienze applicate'),('700','Arti e attività ricreative'),('800','Letteratura'),('900','Storia e geografia')]
        dw=st.text_input('Cerca un codice o un argomento',key='dewey_term_v040')
        matches=[(n,d) for n,d in dewey_classes if dw.strip().casefold() in n.casefold() or dw.strip().casefold() in d.casefold()] if dw.strip() else dewey_classes
        st.dataframe(pd.DataFrame(matches,columns=['Classe','Descrizione']),hide_index=True,use_container_width=True)
        st.caption('Le classi mostrate sono generali: non scegliere un codice dettagliato basandoti solo su questa tabella.')
    with st.expander('✏️ Modifica scheda (prima cerca il volume)'):
        books=options('SELECT id,title,location FROM books WHERE title ILIKE ? OR author ILIKE ? OR location ILIKE ? OR isbn ILIKE ? ORDER BY title LIMIT 50',tuple('%'+term.strip()+'%' for _ in range(4))) if len(term.strip())>=2 else []
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
                        notify_success('Scheda bibliografica aggiornata correttamente.')
            deletion_ui('books',chosen['id'],chosen['title'],'book',soft=True)
    st.info('Importazione Excel e riconciliazione Access/SBN: da sviluppare con anteprima e controlli prima di qualsiasi scrittura nel database.')

elif page=='👥 Utenti':
    st.header('Utenti')
    st.dataframe(fetch('''SELECT id,last_name AS Cognome,first_name AS Nome,reader_type AS "Tipologia utente",course AS Corso,office AS Ufficio,phone AS Telefono,email AS Email,other_contacts AS "Altri recapiti",notes AS Note,reminders_enabled AS "Promemoria (predisposti)" FROM readers ORDER BY last_name,first_name LIMIT 100'''),hide_index=True,use_container_width=True)
    st.caption('Sono mostrati al massimo 100 utenti. Per modificarne uno, utilizza la ricerca qui sotto.')
    types=['Frequentatore','Quadro permanente','Personale civile','Altro']
    with st.expander('➕ Nuovo utente'):
        with st.form('new_reader',clear_on_submit=True):
            last=st.text_input('Cognome *');first=st.text_input('Nome *');kind=st.selectbox('Tipologia utente',types);course=st.text_input('Corso');office=st.text_input('Ufficio')
            phone=st.text_input('Telefono');email=st.text_input('Email');other=st.text_input('Altri recapiti');notes=st.text_area('Note');reminders=st.checkbox('Consenti promemoria email (non attivi nella demo)')
            if st.form_submit_button('Salva utente'):
                if first.strip() and last.strip():
                    execute('''INSERT INTO readers(name,first_name,last_name,reader_type,course,office,phone,email,other_contacts,notes,reminders_enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(first.strip()+' '+last.strip(),first.strip(),last.strip(),kind,course,office,phone,email,other,notes,int(reminders)))
                    notify_success('Nuovo utente registrato correttamente.')
                else:st.error('Nome e cognome sono obbligatori.')
    reader_term=st.text_input('Cerca utente da modificare per nome, cognome o corso',key='reader_search_v040')
    people=options("SELECT id,name,first_name,last_name FROM readers WHERE COALESCE(first_name,'') ILIKE ? OR COALESCE(last_name,'') ILIKE ? OR COALESCE(course,'') ILIKE ? ORDER BY last_name,first_name LIMIT 50",tuple('%'+reader_term.strip()+'%' for _ in range(3))) if len(reader_term.strip())>=2 else []
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
                        notify_success('Dati dell’utente aggiornati correttamente.')
        deletion_ui('readers',chosen['id'],chosen['name'],'reader',linked=[('loans','reader_id')])
        st.subheader('Storico prestiti dell’utente')
        st.dataframe(fetch("SELECT b.title AS Titolo,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi FROM loans l JOIN books b ON b.id=l.book_id WHERE l.reader_id=? ORDER BY l.loan_date DESC",(chosen['id'],)),hide_index=True,use_container_width=True)

elif page=='🔄 Prestiti':
    st.header('Prestiti e restituzioni')
    tab1,tab2,tab3=st.tabs(['Nuovo prestito','Prestiti attivi','Storico completo'])
    with tab1:
        loan_book_search=st.text_input('Cerca volume per titolo, collocazione o ISBN',key='loan_book_search_v040')
        loan_reader_search=st.text_input('Cerca utente per cognome o nome',key='loan_reader_search_v040')
        available=options('''SELECT id,title,location AS inventory FROM books WHERE withdrawn=0 AND
            (title ILIKE ? OR location ILIKE ? OR isbn ILIKE ?) AND
            copies > (SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL)
            ORDER BY title LIMIT 50''',tuple('%'+loan_book_search.strip()+'%' for _ in range(3))) if len(loan_book_search.strip())>=2 else []
        people=options('''SELECT id,name FROM readers WHERE name ILIKE ? OR first_name ILIKE ? OR last_name ILIKE ? ORDER BY name LIMIT 50''',tuple('%'+loan_reader_search.strip()+'%' for _ in range(3))) if len(loan_reader_search.strip())>=2 else []
        if not available or not people:st.info('Cerca un volume disponibile e un utente (almeno 2 caratteri in ciascun campo).')
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
                            c.execute('SELECT pg_advisory_xact_lock(%s)', (int(book['id']),))
                            updated=c.execute('''SELECT CASE WHEN withdrawn=0 AND copies > (SELECT COUNT(*) FROM loans WHERE book_id=? AND returned_at IS NULL) THEN 1 ELSE 0 END FROM books WHERE id=?''',(book['id'],book['id'])).fetchone()[0]
                            if updated: c.execute('INSERT INTO loans(book_id,reader_id,loan_date,due_date) VALUES(?,?,?,?)',(book['id'],person['id'],start.isoformat(),due.isoformat()))
                        if updated:notify_success('Prestito registrato correttamente. Il volume risulta ora in prestito.')
                        else:st.error('Il volume non è più disponibile.')
    with tab2:
        active_search=st.text_input('Filtra prestiti attivi per titolo, collocazione o utente',key='active_loan_search_v040')
        active_like='%'+active_search.strip()+'%'
        current=options('''SELECT l.id,b.title,r.name,l.due_date,l.loan_date,b.location FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id WHERE l.returned_at IS NULL AND (b.title ILIKE ? OR b.location ILIKE ? OR r.name ILIKE ?) ORDER BY l.due_date LIMIT 100''',(active_like,active_like,active_like)) if len(active_search.strip())>=2 else []
        if not current:st.info('Cerca un prestito attivo (almeno 2 caratteri).')
        else:
            for loan in current:
                with st.container(border=True):
                    st.write(f'**{loan["title"]}** — {loan["name"]} · scadenza {loan["due_date"]}')
                    a,b=st.columns(2)
                    if a.button('Registra restituzione',key=f'return_{loan["id"]}'):
                        with connect() as c:
                            changed=c.execute('UPDATE loans SET returned_at=? WHERE id=? AND returned_at IS NULL',(date.today().isoformat(),loan['id'])).rowcount
                            # La disponibilità è calcolata dai prestiti attivi, senza cancellare lo storico.
                        if changed:
                            notify_success('Restituzione registrata correttamente. Il volume è nuovamente disponibile.')
                        else:
                            st.warning('Il prestito risulta già restituito: nessuna modifica effettuata.')
                    with st.expander('Modifica scadenza'):
                        try:
                            existing_due=date.fromisoformat(str(loan['due_date'])[:10])
                        except ValueError:
                            existing_due=date.today()+timedelta(days=30)
                        new_due=st.date_input('Nuova scadenza',value=existing_due,key=f'due_{loan["id"]}')
                        if st.button('Salva nuova scadenza',key=f'save_due_{loan["id"]}'):
                            if new_due < date.fromisoformat(str(loan['loan_date'])[:10]):
                                st.error('La scadenza non può precedere la data del prestito.')
                            else:
                                execute('UPDATE loans SET due_date=? WHERE id=? AND returned_at IS NULL',(new_due.isoformat(),loan['id']))
                                notify_success('Scadenza del prestito aggiornata correttamente.')
                    if b.button('Rinnova di 30 giorni',key=f'renew_{loan["id"]}'):
                        execute('UPDATE loans SET due_date=date(due_date, "+30 days"),renewals=renewals+1 WHERE id=? AND returned_at IS NULL',(loan['id'],));notify_success('Prestito rinnovato correttamente di 30 giorni. Lo storico resta invariato.')
    with tab3:
        st.dataframe(fetch('''SELECT l.id,b.title AS Titolo,r.name AS Utente,l.loan_date AS Prestito,l.due_date AS Scadenza,l.returned_at AS Restituzione,l.renewals AS Rinnovi,CASE WHEN l.returned_at IS NULL THEN 'Attivo' ELSE 'Restituito' END AS Stato FROM loans l JOIN books b ON b.id=l.book_id JOIN readers r ON r.id=l.reader_id ORDER BY l.loan_date DESC'''),hide_index=True,use_container_width=True)
        st.caption('I prestiti restituiti rimangono registrati. In questa demo non è prevista la cancellazione dello storico.')

elif page=='📰 Catalogo periodici':
    st.header('Periodici e spoglio')
    st.caption('Tre livelli collegati: testate → fascicoli → articoli. Solo dati fittizi durante il collaudo.')
    t1,t2,t3=st.tabs(['Testate','Fascicoli','Spoglio articoli'])
    with t1:
        st.dataframe(fetch('''SELECT journal_code AS Codice,title AS Titolo,subtitle AS Sottotitolo,publisher AS Editore,place AS Luogo,start_year AS "Anno inizio",end_year AS "Anno fine",issn AS "ISSN / ISBN",location AS Collocazione,notes AS Note FROM journals ORDER BY title LIMIT 100'''),hide_index=True,use_container_width=True)
        with st.expander('➕ Nuova testata'):
            with st.form('journal_v02'):
                code=st.text_input('ID periodico (es. RIV-001)');title=st.text_input('Titolo *');subtitle=st.text_input('Sottotitolo');publisher=st.text_input('Editore');place=st.text_input('Luogo');start_year=st.text_input('Anno inizio');end_year=st.text_input('Anno fine');issn=st.text_input('ISSN / ISBN');location=st.text_input('Collocazione');notes=st.text_area('Note')
                if st.form_submit_button('Salva testata'):
                    if not code.strip():st.error('Codice periodico obbligatorio.')
                    elif conflict('journals','journal_code',code):st.error('Codice periodico già presente.')
                    elif title.strip():
                        execute('''INSERT INTO journals(journal_code,title,subtitle,publisher,place,start_year,end_year,issn,location,notes) VALUES(?,?,?,?,?,?,?,?,?,?)''',(code,title,subtitle,publisher,place,start_year,end_year,issn,location,notes));notify_success('Testata del periodico salvata correttamente.')
                    else:st.error('Titolo obbligatorio.')
        journal_term=st.text_input('Cerca testata da modificare',key='journal_edit_search')
        journals=options('SELECT id,title,journal_code FROM journals WHERE title ILIKE ? OR journal_code ILIKE ? ORDER BY title LIMIT 50',tuple('%'+journal_term.strip()+'%' for _ in range(2))) if len(journal_term.strip())>=2 else []
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
                            execute('UPDATE journals SET '+','.join(f'{col}=?' for col in fields)+' WHERE id=?',tuple(fields.values())+(chosen['id'],));notify_success('Testata del periodico aggiornata correttamente.')
            deletion_ui('journals',chosen['id'],chosen['title'],'journal',linked=[('issues','journal_id')])
    with t2:
        st.dataframe(fetch('''SELECT i.id,j.journal_code AS "Codice testata",j.title AS Testata,i.issue_code AS "Progressivo",i.year AS Anno,i.volume AS Volume,i.number AS "Numero pubblicato",i.issue_date AS Data,i.pages AS Pagine,i.location AS Collocazione,i.conservation AS Conservazione,i.availability AS Disponibilità,i.conservation_notes AS "Note conservazione",i.notes AS Note FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.title,i.location LIMIT 100'''),hide_index=True,use_container_width=True)
        journal_issue_term=st.text_input('Cerca testata per nuovo fascicolo',key='journal_issue_search')
        journals=options('SELECT id,title,journal_code,location FROM journals WHERE title ILIKE ? OR journal_code ILIKE ? ORDER BY title LIMIT 50',tuple('%'+journal_issue_term.strip()+'%' for _ in range(2))) if len(journal_issue_term.strip())>=2 else []
        if journals:
            j=st.selectbox('Testata per nuovo fascicolo',journals,format_func=lambda x:f"{x['journal_code'] or 'Senza codice'} · {x['title']}",key='new_issue_journal')
            suggested=next_progressive('issues','issue_code','journal_id',j['id'])
            prefix=(j['journal_code'] or '').strip()
            proposed=f'{prefix}-{suggested}' if prefix else ''
            with st.expander('➕ Nuovo fascicolo'):
                st.caption(f'Progressivo proposto: {suggested} · Collocazione proposta: {proposed or "assegnare prima il codice alla testata"}')
                with st.form('issue_v022'):
                    issue_code=st.text_input('Progressivo inventariale (modificabile)',value=suggested);location=st.text_input('Collocazione (lascia vuoto per generarla automaticamente)',value='')
                    year=st.number_input('Anno',1800,2100,2026);volume=st.text_input('Volume');number=st.text_input('Numero pubblicato (anche 5-6)');issue_date=st.text_input('Data (come riportata nel fascicolo)');pages=st.text_input('Pagine')
                    conservation=st.selectbox('Stato di conservazione',['Non valutato','Ottimo','Buono','Discreto','Deteriorato','Da restaurare']);availability=st.selectbox('Disponibilità',['Disponibile','In prestito','Non consultabile','Mancante']);conservation_notes=st.text_area('Note sulla conservazione');notes=st.text_area('Note generali')
                    if st.form_submit_button('Salva fascicolo'):
                        final_location=location.strip() or (f'{prefix}-{issue_code.strip()}' if prefix else '')
                        err=issue_duplicate(j['id'],issue_code,final_location)
                        if not prefix:st.error('Assegna prima un codice alla testata.')
                        elif not issue_code.strip() or not final_location:st.error('Progressivo e collocazione obbligatori.')
                        elif err:st.error(err)
                        else:
                            execute('''INSERT INTO issues(journal_id,issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(j['id'],issue_code.strip(),year,volume,number,issue_date,pages,final_location,conservation,availability,conservation_notes,notes));notify_success('Fascicolo salvato correttamente.')
        issue_edit_term=st.text_input('Cerca fascicolo da modificare per testata o collocazione',key='issue_edit_search')
        issues=options('''SELECT i.id,j.title,i.issue_code,i.year,i.number,i.location FROM issues i JOIN journals j ON j.id=i.journal_id WHERE j.title ILIKE ? OR i.location ILIKE ? ORDER BY j.title,i.year DESC LIMIT 50''',tuple('%'+issue_edit_term.strip()+'%' for _ in range(2))) if len(issue_edit_term.strip())>=2 else []
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
                            execute('''UPDATE issues SET issue_code=?,year=?,volume=?,number=?,issue_date=?,pages=?,location=?,conservation=?,availability=?,conservation_notes=?,notes=? WHERE id=?''',(issue_code,year,volume,number,issue_date,pages,location,conservation,availability,conservation_notes,notes,selected['id']));notify_success('Fascicolo aggiornato correttamente.')
            deletion_ui('issues',selected['id'],str(selected['title'])+' / '+str(selected['year']),'issue',linked=[('articles','issue_id')])
    with t3:
        term=st.text_input('Cerca articoli per titolo, autore, parole chiave, Dewey, testata')
        q='''SELECT j.title AS Testata,i.location AS "Collocazione fascicolo",i.year AS Anno,i.number AS "Numero fascicolo",a.article_code AS "Progressivo articolo",a.author AS Autori,a.title AS Articolo,a.pages AS Pagine,a.keywords AS "Parole chiave",a.dewey AS Dewey,a.notes AS Note FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id'''
        params=()
        if term.strip():
            q+=' WHERE '+' OR '.join(f"COALESCE({col}, '') ILIKE ?" for col in ['a.title','a.author','a.keywords','a.dewey','j.title','i.location'])
            params=tuple('%'+term.strip()+'%' for _ in range(6))
        st.dataframe(fetch(q+' ORDER BY j.title,i.location,a.article_code LIMIT 100',params) if len(term.strip())>=2 else pd.DataFrame(),hide_index=True,use_container_width=True)
        article_issue_term=st.text_input('Cerca fascicolo per nuovo articolo',key='article_issue_search')
        issues=options('''SELECT i.id,j.title,i.location,i.issue_code,i.year,i.number FROM issues i JOIN journals j ON j.id=i.journal_id WHERE j.title ILIKE ? OR i.location ILIKE ? ORDER BY j.title,i.year DESC LIMIT 50''',tuple('%'+article_issue_term.strip()+'%' for _ in range(2))) if len(article_issue_term.strip())>=2 else []
        if issues:
            issue=st.selectbox('Fascicolo per nuovo articolo',issues,format_func=lambda x:f"{x['title']} · {x['location'] or 'senza collocazione'} · {x['year']} / {x['number'] or '—'}",key='new_article_issue')
            suggested=next_progressive('articles','article_code','issue_id',issue['id'])
            st.caption(f"Codice proposto: {(issue['location'] or 'FASCICOLO')}-{suggested}")
            with st.expander('➕ Nuovo articolo'):
                with st.form('article_v022',clear_on_submit=True):
                    article_code=st.text_input('Progressivo articolo (modificabile)',value=suggested);author=st.text_input('Autori');title=st.text_input('Titolo articolo *');pages=st.text_input('Pagine');keywords=st.text_input('Parole chiave');dewey=st.text_input('Classificazione Dewey');notes=st.text_area('Note')
                    if st.form_submit_button('Salva articolo'):
                        if not title.strip() or not article_code.strip():st.error('Titolo e progressivo obbligatori.')
                        elif article_duplicate(issue['id'],article_code):st.error('Progressivo articolo già presente in questo fascicolo.')
                        else:
                            execute('''INSERT INTO articles(issue_id,article_code,author,title,pages,keywords,dewey,notes) VALUES(?,?,?,?,?,?,?,?)''',(issue['id'],article_code.strip(),author,title,pages,keywords,dewey,notes));notify_success('Articolo registrato correttamente nello spoglio.')
        article_edit_term=st.text_input('Cerca articolo da modificare per titolo o autore',key='article_edit_search')
        articles=options('SELECT id,title FROM articles WHERE title ILIKE ? OR author ILIKE ? ORDER BY title LIMIT 50',tuple('%'+article_edit_term.strip()+'%' for _ in range(2))) if len(article_edit_term.strip())>=2 else []
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
                            execute('UPDATE articles SET article_code=?,author=?,title=?,pages=?,keywords=?,dewey=?,notes=? WHERE id=?',(code,author,title,pages,keywords,dewey,notes,selected['id']));notify_success('Articolo aggiornato correttamente.')
            deletion_ui('articles',selected['id'],selected['title'],'article')

elif page=='📥 Anteprima inventari':
    st.header('Anteprima registri inventariali Excel')
    st.info('Modalità di verifica: non scrive alcun dato in Supabase. I fogli SCARICO sono sempre esclusi.')
    uploaded=st.file_uploader('Carica un registro Excel .xlsx',type=['xlsx'],key='inventory_preview')
    if uploaded:
        try:
            entries,used,skipped=_register_rows(uploaded)
            st.write('**Registri letti:** '+(', '.join(used) if used else 'nessuno'))
            st.write('**Fogli esclusi:** '+(', '.join(skipped) if skipped else 'nessuno'))
            if not used:
                st.error('Nessun foglio di registro riconosciuto: sono ammessi solo nomi che iniziano con REG.')
            else:
                problems=sum(bool(r['Anomalie']) for r in entries)
                a,b,c=st.columns(3)
                a.metric('Schede individuate',len(entries))
                b.metric('Da verificare',problems)
                c.metric('Senza anomalie locali',len(entries)-problems)
                st.caption('Le anomalie sono rilevate nel file, non ancora confrontate con il database.')
                df=pd.DataFrame(entries)
                st.dataframe(df,hide_index=True,use_container_width=True)
                buf=io.BytesIO()
                with pd.ExcelWriter(buf,engine='openpyxl') as writer:
                    df.to_excel(writer,index=False,sheet_name='Anteprima')
                st.download_button('⬇️ Scarica anteprima e anomalie',buf.getvalue(),file_name='anteprima_registri_isma.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                st.warning('Importazione definitiva disabilitata: occorre prima validare la mappatura, i duplicati nel database e il piano di ripristino.')
        except Exception:
            st.error('Lettura del file non riuscita. Controlla il formato Excel e le intestazioni dei registri.')

elif page=='🏷️ Etichette':
    st.header('Etichette per libri e periodici')
    st.caption('Generazione PDF A4 per stampa. Misure regolabili: verificare il primo foglio su carta normale prima di usare adesivi.')
    label_type=st.selectbox('Tipo di etichetta',['Dorso','Inventario','Fascicolo'])
    search=st.text_input('Cerca per titolo o collocazione (almeno 2 caratteri)',key='labels_search')
    records=[]
    if len(search.strip())>=2:
        like='%'+search.strip()+'%'
        if label_type=='Fascicolo':
            records=options("SELECT i.id, i.location, j.title, CAST('' AS TEXT) AS register_number FROM issues i JOIN journals j ON j.id=i.journal_id WHERE i.location ILIKE ? OR j.title ILIKE ? ORDER BY i.location LIMIT 100",(like,like))
        else:
            records=options('SELECT id,location,title,register_number FROM books WHERE location ILIKE ? OR title ILIKE ? ORDER BY location LIMIT 100',(like,like))
    if records:
        selected_ids=st.multiselect('Seleziona le schede da stampare',options=[r['id'] for r in records],format_func=lambda v:next((str(r['location'])+' - '+str(r['title']) for r in records if r['id']==v),str(v)))
        chosen=[r for r in records if r['id'] in selected_ids]
        a,b,c=st.columns(3)
        width=a.number_input('Larghezza etichetta (mm)',10,100,45)
        height=b.number_input('Altezza etichetta (mm)',10,80,22)
        cols=c.number_input('Colonne per foglio',1,10,4)
        d,e,f=st.columns(3)
        rows=d.number_input('Righe per foglio',1,30,11)
        left=e.number_input('Margine sinistro (mm)',0,60,12)
        top=f.number_input('Margine superiore (mm)',0,60,12)
        gx,gy=st.columns(2)
        gap_x=gx.number_input('Spazio orizzontale (mm)',0,30,2)
        gap_y=gy.number_input('Spazio verticale (mm)',0,30,2)
        if chosen:
            try:
                pdf_data=build_labels_pdf(chosen,width,height,cols,rows,left,top,gap_x,gap_y,label_type)
                st.download_button('⬇️ Scarica PDF etichette',pdf_data,file_name='etichette_isma.pdf',mime='application/pdf')
            except ValueError as exc:st.error(str(exc))
    elif search.strip():st.info('Nessuna scheda trovata. Affina la ricerca.')
    else:st.info('Cerca un libro o fascicolo per preparare le etichette.')
    st.warning('Il formato del modello .xls allegato deve ancora essere verificato: le misure preimpostate sono provvisorie.')

elif page=='📤 Esporta Excel':
    st.header('Esportazione dati in Excel')
    st.caption('Scarica un archivio in formato XLSX. Contiene anche recapiti e note: conservarlo in modo protetto.')
    st.subheader('Riepilogo registrazioni')
    table_names={'Monografie':'books','Testate':'journals','Fascicoli':'issues','Articoli':'articles','Utenti':'readers','Prestiti':'loans'}
    counts={label:int(fetch(f'SELECT COUNT(*) AS n FROM {table}').iloc[0,0]) for label,table in table_names.items()}
    st.dataframe(pd.DataFrame([{'Archivio':k,'Registrazioni attuali':v} for k,v in counts.items()]),hide_index=True,use_container_width=True)
    st.caption('I conteggi si riferiscono al database Supabase condiviso.')
    datasets={
      'Monografie':"""SELECT id AS ID,title AS Titolo,author AS Autore,isbn AS ISBN,publisher AS Editore,year AS Anno,subject AS Soggetto,classification AS Classificazione,section AS Sezione,location AS Collocazione,register_number AS "N. registro inventariale",sbn_inventory AS "Inventario SBN",register_source AS "Registro di provenienza",work_group AS "Codice opera multivolume",volume_label AS Volume,copies AS Copie,(copies-(SELECT COUNT(*) FROM loans l WHERE l.book_id=books.id AND l.returned_at IS NULL)) AS Disponibili,notes AS Note,withdrawn AS Dismesso FROM books ORDER BY section,location""",
      'Testate':"""SELECT id AS ID,journal_code AS "Codice testata",title AS "Titolo testata",subtitle AS Sottotitolo,publisher AS Editore,place AS Luogo,start_year AS "Anno inizio",end_year AS "Anno fine",issn AS ISSN,location AS Collocazione,notes AS Note FROM journals ORDER BY journal_code""",
      'Fascicoli':"""SELECT i.id AS ID,j.journal_code AS "Codice testata",j.title AS "Titolo testata",i.issue_code AS "Progressivo fascicolo",i.location AS "Collocazione fascicolo",i.year AS Anno,i.volume AS Volume,i.number AS "Numero pubblicato",i.issue_date AS Data,i.pages AS Pagine,i.conservation AS Conservazione,i.availability AS Disponibilità,i.conservation_notes AS "Note conservazione",i.notes AS Note FROM issues i JOIN journals j ON j.id=i.journal_id ORDER BY j.journal_code,i.location""",
      'Articoli':"""SELECT a.id AS ID,j.journal_code AS "Codice testata",j.title AS "Titolo testata",i.location AS "Collocazione fascicolo",i.issue_code AS "Progressivo fascicolo",i.year AS "Anno fascicolo",i.number AS "Numero pubblicato",a.article_code AS "Progressivo articolo",CASE WHEN i.location IS NOT NULL AND TRIM(i.location)<>'' AND a.article_code IS NOT NULL AND TRIM(a.article_code)<>'' THEN i.location||'-'||a.article_code ELSE NULL END AS "Codice articolo completo",a.title AS "Titolo articolo",a.author AS Autori,a.pages AS Pagine,a.keywords AS "Parole chiave",a.dewey AS Dewey,a.notes AS Note FROM articles a JOIN issues i ON i.id=a.issue_id JOIN journals j ON j.id=i.journal_id ORDER BY j.journal_code,i.location,a.article_code""",
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
        st.download_button('⬇️ Scarica Excel',buffer.getvalue(),file_name='biblioteca_isma_collaudo_v040.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.info('Questa esportazione non sostituisce il backup tecnico del database.')
    st.info('Backup PostgreSQL: da configurare e verificare separatamente. Non è disponibile la copia SQLite della vecchia demo.')

else:
    st.header('Informazioni sul prototipo')
    st.write('Versione 0.4.1: ricerca monografie limitata, recupero ISBN e consultazione delle classi Dewey principali. Database invariato.')
    st.write('Non ancora implementati o validati: backup e ripristino, importazione definitiva Access/Excel/SBN, tavole Dewey dettagliate, registro operazioni, prestiti periodici, promemoria email e revisione sicurezza per dati reali.')
    st.info('Per la versione operativa serviranno verifiche di autorizzazione, sicurezza e trattamento dei dati dell’Amministrazione.')
