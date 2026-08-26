import io, json, sqlite3, datetime
import pandas as pd
import streamlit as st
from openpyxl import Workbook
from radar_engine import extract_pdf_text, extract_fields, score

st.set_page_config(page_title='Radar Crisi d’Impresa', page_icon='📊', layout='wide')
st.markdown('''<style>
.block-container{max-width:1180px;padding-top:2rem}.bigtitle{font-size:2.2rem;font-weight:750}.sub{color:#666;margin-bottom:1.4rem}.stMetric{border:1px solid #e7e7e7;border-radius:12px;padding:12px;background:white}
</style>''', unsafe_allow_html=True)
st.markdown('<div class="bigtitle">Radar Crisi d’Impresa</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Special Situations & Turnaround Intelligence — prototipo web 2.1</div>', unsafe_allow_html=True)

@st.cache_resource
def dbconn():
    c=sqlite3.connect('radar_targets.db', check_same_thread=False)
    c.execute('CREATE TABLE IF NOT EXISTS targets(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, company TEXT, score REAL, class TEXT, fit TEXT, data TEXT)')
    return c

TAB1,TAB2=st.tabs(['Analizza bilancio','Portafoglio target'])
with TAB1:
    up=st.file_uploader('Carica il bilancio PDF', type=['pdf'], help='Puoi trascinare qui il PDF oppure selezionarlo dal computer.')
    if up:
        if st.button('ANALIZZA BILANCIO', type='primary', use_container_width=True):
            with st.spinner('Lettura del bilancio e OCR delle pagine necessarie...'):
                text, used_ocr=extract_pdf_text(up.getvalue(), ocr=True)
                fields=extract_fields(text)
                st.session_state['fields']=fields; st.session_state['ocr']=used_ocr; st.session_state['filename']=up.name
        if 'fields' in st.session_state:
            f=st.session_state['fields']
            st.info('OCR utilizzato: sì' if st.session_state.get('ocr') else 'PDF testuale: OCR non necessario')
            st.subheader('1. Verifica i dati riconosciuti')
            c1,c2,c3=st.columns(3)
            with c1:
                f['ragione_sociale']=st.text_input('Ragione sociale', f.get('ragione_sociale') or '')
                f['ricavi_correnti']=st.number_input('Ricavi (€)', value=float(f.get('ricavi_correnti') or 0), step=1000.0)
                f['ebitda']=st.number_input('EBITDA / proxy (€)', value=float(f.get('ebitda') or 0), step=1000.0)
                f['risultato_netto']=st.number_input('Risultato netto (€)', value=float(f.get('risultato_netto') or 0), step=1000.0)
            with c2:
                f['debito_finanziario']=st.number_input('Debito finanziario (€)', value=float(f.get('debito_finanziario') or 0), step=1000.0)
                f['debiti_tributari']=st.number_input('Debiti tributari (€)', value=float(f.get('debiti_tributari') or 0), step=1000.0)
                f['debiti_previdenziali']=st.number_input('Debiti previdenziali (€)', value=float(f.get('debiti_previdenziali') or 0), step=1000.0)
                f['debiti_fornitori']=st.number_input('Debiti fornitori (€)', value=float(f.get('debiti_fornitori') or 0), step=1000.0)
            with c3:
                f['patrimonio_netto']=st.number_input('Patrimonio netto (€)', value=float(f.get('patrimonio_netto') or 0), step=1000.0)
                f['attivo_circolante']=st.number_input('Attivo circolante (€)', value=float(f.get('attivo_circolante') or 0), step=1000.0)
                f['passivita_correnti']=st.number_input('Passività correnti (€)', value=float(f.get('passivita_correnti') or 0), step=1000.0)
                f['oneri_finanziari']=st.number_input('Oneri finanziari (€)', value=float(f.get('oneri_finanziari') or 0), step=1000.0)
            st.subheader('2. Valutazioni professionali preliminari')
            q1,q2,q3,q4=st.columns(4)
            qual={}
            with q1: qual['continuita']=st.slider('Continuità aziendale',1,5,3)
            with q2: qual['ristrutturabilita']=st.slider('Ristrutturabilità debito',1,5,3)
            with q3: qual['asset_strategici']=st.slider('Asset strategici',1,5,3)
            with q4: qual['fattibilita_deal']=st.slider('Fattibilità operazione',1,5,3)
            qual['red_flag']=st.checkbox('Red flag grave / KO preliminare')
            sc=score(f,qual)
            st.subheader('3. Risultato Radar')
            m1,m2,m3,m4=st.columns(4)
            m1.metric('Punteggio Radar',f"{sc['totale']}/100")
            m2.metric('Classe',sc['classe'])
            m3.metric('Turnaround fiscale',sc['fit'])
            m4.metric('Distress composito',f"{sc['composito']}/40")
            cols=st.columns(3)
            cols[0].write(f"**Distress finanziario:** {sc['finanziario']}/15")
            cols[0].write(f"**Distress fiscale:** {sc['fiscale']}/15")
            cols[0].write(f"**Distress commerciale:** {sc['commerciale']}/10")
            cols[1].write(f"**Continuità:** {sc['continuita']}/20")
            cols[1].write(f"**Ristrutturabilità:** {sc['ristrutturabilita']}/20")
            cols[2].write(f"**Asset:** {sc['asset']}/10")
            cols[2].write(f"**Fattibilità:** {sc['fattibilita']}/10")
            if sc['fit']=='FIT-A': st.success('Target ad alta priorità per approfondimento di turnaround fiscale. Il risultato non equivale a raccomandazione di acquisto.')
            elif sc['fit']=='FIT-B': st.warning('Target potenzialmente coerente con la strategia, ma richiede ulteriore verifica.')
            else: st.error('Compatibilità preliminare bassa con la strategia turnaround fiscale.')
            a,b=st.columns(2)
            if a.button('SALVA TARGET', use_container_width=True):
                dbconn().execute('INSERT INTO targets(created,company,score,class,fit,data) VALUES(?,?,?,?,?,?)',(datetime.datetime.now().isoformat(timespec='seconds'), f.get('ragione_sociale') or up.name,sc['totale'],sc['classe'],sc['fit'],json.dumps({'fields':f,'score':sc},ensure_ascii=False)))
                dbconn().commit(); st.success('Target salvato nel portafoglio.')
            # Excel export
            wb=Workbook(); ws=wb.active; ws.title='SCHEDA_RADAR'
            ws.append(['RADAR CRISI D’IMPRESA — SCHEDA TARGET','Valore'])
            for k,v in f.items(): ws.append([k,v])
            ws.append([])
            for k,v in sc.items(): ws.append([k,v])
            bio=io.BytesIO(); wb.save(bio); bio.seek(0)
            b.download_button('ESPORTA EXCEL',bio,file_name=f"Radar_{(f.get('ragione_sociale') or 'Target').replace(' ','_')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
with TAB2:
    df=pd.read_sql_query('SELECT id,created,company,score,class,fit FROM targets ORDER BY score DESC, id DESC',dbconn())
    if df.empty: st.info('Nessun target salvato.')
    else: st.dataframe(df, use_container_width=True, hide_index=True)

st.caption('Strumento di screening preliminare. I dati estratti via OCR devono essere verificati prima di qualsiasi decisione professionale o di investimento.')
