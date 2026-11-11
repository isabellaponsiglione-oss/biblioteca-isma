"""Biblioteca ISMA - diagnostic read-only for Supabase PostgreSQL."""
import streamlit as st
import psycopg
from psycopg.rows import dict_row

st.set_page_config(page_title='Biblioteca ISMA | Test Supabase', page_icon='📚')
st.title('📚 Biblioteca ISMA — Test Supabase')
st.caption('Test tecnico 0.2.4 • Sola lettura • Nessun dato reale')
st.warning('Questa pagina NON è il gestionale. Non inserire dati reali o riservati.')

# No credentials are displayed, logged or sent to the browser.
if 'DATABASE_URL' not in st.secrets:
    st.info('Connessione non configurata. Aggiungi DATABASE_URL nei Secrets di questa app Streamlit.')
    st.stop()

if st.button('Verifica collegamento e sei tabelle'):
    try:
        with psycopg.connect(st.secrets['DATABASE_URL'], connect_timeout=10, sslmode='require', row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database() AS db, current_schema() AS schema')
                info = cur.fetchone()
                tables = ('books', 'journals', 'issues', 'articles', 'readers', 'loans')
                results = []
                for table in tables:
                    cur.execute('SELECT to_regclass(%s) IS NOT NULL AS present', (f'public.{table}',))
                    present = cur.fetchone()['present']
                    count = None
                    if present:
                        # Only fixed, developer-defined table identifiers are interpolated.
                        cur.execute(f'SELECT COUNT(*) AS n FROM public.{table}')
                        count = cur.fetchone()['n']
                    results.append({'Tabella': table, 'Presente': 'Sì' if present else 'No', 'Registrazioni': count})
        st.success('Connessione PostgreSQL riuscita.')
        st.write('Database:', info['db'])
        st.dataframe(results, hide_index=True, use_container_width=True)
        if all(row['Presente'] == 'Sì' for row in results):
            st.success('Tutte e sei le tabelle sono accessibili in sola lettura.')
        else:
            st.error('Almeno una tabella non è disponibile.')
    except Exception:
        # Never echo database exceptions: some drivers include connection details.
        st.error('Connessione o verifica non riuscita. Controlla i Secrets e il Session pooler; non pubblicare password o log completi.')
