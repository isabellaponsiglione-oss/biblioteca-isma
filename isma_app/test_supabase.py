"""Biblioteca ISMA - test authentication + PostgreSQL connectivity, non-operational."""
import streamlit as st
import psycopg
from psycopg.rows import dict_row
import requests

st.set_page_config(page_title='Biblioteca ISMA | Test accessi', page_icon='📚')
st.title('📚 Biblioteca ISMA — Test accessi')
st.caption('Versione tecnica 0.2.5 • Verifica autenticazione • Sola lettura')
st.warning('Pagina di prova, non gestionale. Non inserire dati bibliografici o personali reali.')

needed = ('SUPABASE_URL', 'SUPABASE_ANON_KEY', 'DATABASE_URL')
if any(k not in st.secrets for k in needed):
    st.error('Configurazione incompleta: occorrono SUPABASE_URL, SUPABASE_ANON_KEY e DATABASE_URL nei Secrets di questa app.')
    st.stop()

base = str(st.secrets['SUPABASE_URL']).rstrip('/')
key = str(st.secrets['SUPABASE_ANON_KEY'])
headers = {'apikey': key, 'Content-Type': 'application/json'}

if 'access_token' not in st.session_state:
    st.session_state.access_token = None

def current_user(token):
    try:
        response = requests.get(base + '/auth/v1/user', headers={**headers, 'Authorization': 'Bearer ' + token}, timeout=10)
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass
    return None

user = current_user(st.session_state.access_token) if st.session_state.access_token else None
if not user:
    st.session_state.access_token = None
    with st.form('login'):
        email = st.text_input('Email operatore').strip()
        password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Accedi')
    if submitted:
        try:
            response = requests.post(base + '/auth/v1/token?grant_type=password', headers=headers,
                                     json={'email': email, 'password': password}, timeout=12)
            payload = response.json()
            if response.ok and payload.get('access_token'):
                st.session_state.access_token = payload['access_token']
                st.rerun()
            else:
                st.error('Accesso non riuscito. Verifica email e password.')
        except (requests.RequestException, ValueError):
            st.error('Servizio di autenticazione temporaneamente non raggiungibile.')
    st.stop()

st.success('Accesso autenticato.')
st.write('Operatore:', user.get('email', 'Account autenticato'))
if st.button('Esci'):
    st.session_state.access_token = None
    st.rerun()

st.info('Questo test verifica gli account e la connessione tecnica. Le regole di autorizzazione ai dati non sono ancora configurate.')
if st.button('Verifica collegamento e sei tabelle'):
    try:
        with psycopg.connect(st.secrets['DATABASE_URL'], connect_timeout=10, sslmode='require', row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                results = []
                for table in ('books', 'journals', 'issues', 'articles', 'readers', 'loans'):
                    cur.execute('SELECT to_regclass(%s) IS NOT NULL AS present', (f'public.{table}',))
                    present = cur.fetchone()['present']
                    count = None
                    if present:
                        cur.execute(f'SELECT COUNT(*) AS n FROM public.{table}')
                        count = cur.fetchone()['n']
                    results.append({'Tabella': table, 'Presente': 'Sì' if present else 'No', 'Registrazioni': count})
        st.dataframe(results, hide_index=True, width='stretch')
        st.success('Verifica tecnica completata.')
    except Exception:
        st.error('Verifica non riuscita. Controlla la configurazione senza condividere credenziali o log completi.')
