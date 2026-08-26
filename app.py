import io, json, sqlite3, datetime
import pandas as pd
import streamlit as st
from openpyxl import Workbook
from radar_engine import extract_pdf_text, extract_fields_with_meta, validate_extraction, score, it_num

VERSION = '2.2'
st.set_page_config(page_title='Radar Crisi d’Impresa', page_icon='📊', layout='wide')
st.markdown('''<style>
.block-container{max-width:1180px;padding-top:2rem}.bigtitle{font-size:2.2rem;font-weight:750}.sub{color:#666;margin-bottom:1.4rem}.stMetric{border:1px solid #e7e7e7;border-radius:12px;padding:12px;background:white}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="bigtitle">Radar Crisi d’Impresa</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub">Special Situations & Turnaround Intelligence — web {VERSION}</div>', unsafe_allow_html=True)

@st.cache_resource
def dbconn():
    c = sqlite3.connect('radar_targets.db', check_same_thread=False)
    c.execute('CREATE TABLE IF NOT EXISTS targets(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, company TEXT, score REAL, class TEXT, fit TEXT, data TEXT)')
    return c

def fmt(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f'{v:,.0f}'.replace(',', '.') if isinstance(v, (int,float)) else str(v)

def parse_money(s):
    s = (s or '').strip()
    if not s:
        return None
    return it_num(s)

FIELD_UI = [
    ('ragione_sociale','Ragione sociale','text'),
    ('ricavi_correnti','Ricavi (€)','money'),
    ('ebitda','EBITDA / proxy (€)','money'),
    ('risultato_netto','Risultato netto (€)','money'),
    ('liquidita','Liquidità (€)','money'),
    ('debito_finanziario','Debito finanziario (€)','money'),
    ('debiti_tributari','Debiti tributari (€)','money'),
    ('debiti_previdenziali','Debiti previdenziali (€)','money'),
    ('debiti_fornitori','Debiti fornitori (€)','money'),
    ('patrimonio_netto','Patrimonio netto (€)','money'),
    ('attivo_circolante','Attivo circolante (€)','money'),
    ('passivita_correnti','Passività correnti (€)','money'),
    ('oneri_finanziari','Oneri finanziari (€)','money'),
]

TAB1, TAB2 = st.tabs(['Analizza bilancio','Portafoglio target'])
with TAB1:
    up = st.file_uploader('Carica il bilancio PDF', type=['pdf'], help='Trascina qui il PDF oppure selezionalo dal computer.')
    if up:
        if st.button('ANALIZZA BILANCIO', type='primary', use_container_width=True):
            with st.spinner('Lettura del bilancio e OCR delle pagine necessarie...'):
                text, used_ocr = extract_pdf_text(up.getvalue(), ocr=True)
                fields, meta = extract_fields_with_meta(text)
                st.session_state['fields_raw'] = fields
                st.session_state['meta'] = meta
                st.session_state['ocr'] = used_ocr
                st.session_state['filename'] = up.name
                # Initialize edit buffer. Missing remains blank, never zero.
                st.session_state['edit'] = {k: (v if k == 'ragione_sociale' else fmt(v)) for k,v in fields.items() if k in [x[0] for x in FIELD_UI]}
        if 'fields_raw' in st.session_state:
            raw = st.session_state['fields_raw']
            meta = st.session_state.get('meta', {})
            st.info('OCR utilizzato: sì' if st.session_state.get('ocr') else 'PDF testuale: OCR non necessario')
            st.subheader('1. Verifica i dati riconosciuti')
            st.caption('Campo vuoto = dato non trovato. Lo zero va inserito soltanto se il valore è realmente zero.')
            cols = st.columns(3)
            edited = {}
            for idx,(key,label,typ) in enumerate(FIELD_UI):
                with cols[idx % 3]:
                    default = st.session_state['edit'].get(key, '')
                    val = st.text_input(label, value=default, key=f'edit_{key}')
                    edited[key] = val if typ == 'text' else parse_money(val)
                    e = meta.get('evidence',{}).get(key)
                    if e:
                        st.caption(f"Riconoscimento {int(e['confidence']*100)}%")
                    elif typ != 'text':
                        st.caption('Dato non trovato automaticamente')
            quality = validate_extraction(edited, meta.get('evidence',{}))
            if quality['reliable']:
                st.success(f"Affidabilità estrazione preliminare: ADEGUATA — completezza {quality['completeness']*100:.0f}%")
            else:
                st.warning(f"Affidabilità estrazione preliminare: DA VERIFICARE — completezza {quality['completeness']*100:.0f}%")
            for w in quality['warnings']:
                st.warning(w)

            with st.expander('Mostra evidenze di estrazione'):
                rows=[]
                for k,e in meta.get('evidence',{}).items():
                    rows.append({'Voce':k,'Confidenza':f"{e['confidence']*100:.0f}%",'Evidenza':e['evidence']})
                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.subheader('2. Valutazioni professionali preliminari')
            q1,q2,q3,q4 = st.columns(4)
            qual = {}
            with q1: qual['continuita'] = st.slider('Continuità aziendale',1,5,3)
            with q2: qual['ristrutturabilita'] = st.slider('Ristrutturabilità debito',1,5,3)
            with q3: qual['asset_strategici'] = st.slider('Asset strategici',1,5,3)
            with q4: qual['fattibilita_deal'] = st.slider('Fattibilità operazione',1,5,3)
            qual['red_flag'] = st.checkbox('Red flag grave / KO preliminare')

            confirmed = st.checkbox('Confermo di avere verificato i valori sopra riportati prima dello scoring')
            if confirmed:
                sc = score(edited, qual)
                st.subheader('3. Risultato Radar')
                m1,m2,m3,m4 = st.columns(4)
                m1.metric('Punteggio Radar', f"{sc['totale']}/100")
                m2.metric('Classe', sc['classe'])
                m3.metric('Turnaround fiscale', sc['fit'])
                m4.metric('Distress composito', f"{sc['composito']}/40")
                c = st.columns(3)
                c[0].write(f"**Distress finanziario:** {sc['finanziario']}/15")
                c[0].write(f"**Distress fiscale:** {sc['fiscale']}/15")
                c[0].write(f"**Distress commerciale:** {sc['commerciale']}/10")
                c[1].write(f"**Continuità:** {sc['continuita']}/20")
                c[1].write(f"**Ristrutturabilità:** {sc['ristrutturabilita']}/20")
                c[2].write(f"**Asset:** {sc['asset']}/10")
                c[2].write(f"**Fattibilità:** {sc['fattibilita']}/10")
                if not quality['reliable']:
                    st.warning('Lo scoring è stato calcolato su dati confermati manualmente, ma l’estrazione automatica non ha superato tutti i controlli di affidabilità.')
                if sc['fit'] == 'FIT-A':
                    st.success('Target ad alta priorità per approfondimento di turnaround fiscale. Il risultato non equivale a raccomandazione di acquisto.')
                elif sc['fit'] == 'FIT-B':
                    st.warning('Target potenzialmente coerente con la strategia, ma richiede ulteriore verifica.')
                else:
                    st.error('Compatibilità preliminare bassa con la strategia turnaround fiscale.')

                a,b = st.columns(2)
                if a.button('SALVA TARGET', use_container_width=True):
                    payload = {'fields': edited, 'score': sc, 'quality': quality, 'source_file': up.name}
                    dbconn().execute('INSERT INTO targets(created,company,score,class,fit,data) VALUES(?,?,?,?,?,?)',(
                        datetime.datetime.now().isoformat(timespec='seconds'), edited.get('ragione_sociale') or up.name,
                        sc['totale'],sc['classe'],sc['fit'],json.dumps(payload,ensure_ascii=False)))
                    dbconn().commit()
                    st.success('Target salvato nel portafoglio.')
                wb = Workbook(); ws = wb.active; ws.title = 'SCHEDA_RADAR'
                ws.append(['RADAR CRISI D’IMPRESA — SCHEDA TARGET','Valore'])
                for k,v in edited.items(): ws.append([k,v])
                ws.append([]); ws.append(['QUALITA_ESTRAZIONE', f"{quality['completeness']*100:.0f}%"])
                for k,v in sc.items(): ws.append([k,v])
                bio=io.BytesIO(); wb.save(bio); bio.seek(0)
                b.download_button('ESPORTA EXCEL', bio, file_name=f"Radar_{(edited.get('ragione_sociale') or 'Target').replace(' ','_')}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
            else:
                st.info('Lo scoring resta bloccato finché non confermi la verifica dei dati estratti.')

with TAB2:
    df = pd.read_sql_query('SELECT id,created,company,score,class,fit FROM targets ORDER BY score DESC, id DESC', dbconn())
    if df.empty:
        st.info('Nessun target salvato.')
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

st.caption('Strumento di screening preliminare. I dati estratti via OCR devono essere verificati prima di qualsiasi decisione professionale o di investimento.')
