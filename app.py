import io
import datetime
import pandas as pd
import streamlit as st
from radar_engine import extract_pdf_text, extract_fields_with_meta, validate_extraction, score, it_num
from security import require_login, logout_button
from reporting import decision_level, distress_profile, build_ratios, build_thesis, document_checklist, make_excel

VERSION='3.1'
st.set_page_config(page_title='Radar Crisi d’Impresa', page_icon='📊', layout='wide')
st.markdown('''<style>
.block-container{max-width:1250px;padding-top:1.5rem}.title{font-size:2.25rem;font-weight:760}.sub{color:#666;margin-bottom:1rem}.kpi{border:1px solid #e7e7e7;border-radius:12px;padding:12px}.decision{font-size:1.35rem;font-weight:750;padding:.7rem 1rem;border-radius:10px;background:#f4f4f4}.small{font-size:.88rem;color:#666}
</style>''', unsafe_allow_html=True)
require_login()
logout_button()
st.markdown('<div class="title">Radar Crisi d’Impresa</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub">Special Situations & Turnaround Intelligence — web {VERSION}</div>', unsafe_allow_html=True)
st.info('Privacy by design: il PDF viene elaborato in memoria durante la sessione e non viene salvato nel portafoglio. Il portafoglio della 3.1 è di sessione e si perde al riavvio dell’app, salvo esportazione manuale.')

if 'portfolio' not in st.session_state: st.session_state['portfolio']=[]

def fmt(v):
    if v is None: return ''
    if isinstance(v,float) and v.is_integer(): v=int(v)
    return f'{v:,.0f}'.replace(',','.') if isinstance(v,(int,float)) else str(v)

def parse_money(s):
    s=(s or '').strip()
    return None if not s else it_num(s)

FIELD_UI=[
('ragione_sociale','Ragione sociale','text'),('ricavi_correnti','Ricavi (€)','money'),('ebitda','EBITDA / proxy (€)','money'),('risultato_netto','Risultato netto (€)','money'),('liquidita','Liquidità (€)','money'),('debito_finanziario','Debito finanziario (€)','money'),('debiti_tributari','Debiti tributari (€)','money'),('debiti_previdenziali','Debiti previdenziali (€)','money'),('debiti_fornitori','Debiti fornitori (€)','money'),('patrimonio_netto','Patrimonio netto (€)','money'),('attivo_circolante','Attivo circolante (€)','money'),('passivita_correnti','Passività correnti (€)','money'),('oneri_finanziari','Oneri finanziari (€)','money')]

T1,T2,T3=st.tabs(['Analizza bilancio','Portafoglio sessione','Metodo & sicurezza'])
with T1:
    up=st.file_uploader('Carica il bilancio PDF',type=['pdf'],help='Il documento viene elaborato in memoria; non viene inserito nel portafoglio.')
    if up:
        if st.button('ANALIZZA BILANCIO',type='primary',use_container_width=True):
            with st.spinner('Lettura del bilancio e OCR delle pagine necessarie...'):
                text,used_ocr=extract_pdf_text(up.getvalue(),ocr=True)
                fields,meta=extract_fields_with_meta(text)
                st.session_state['fields_raw']=fields; st.session_state['meta']=meta; st.session_state['ocr']=used_ocr; st.session_state['filename']=up.name
                st.session_state['edit']={k:(v if k=='ragione_sociale' else fmt(v)) for k,v in fields.items() if k in [x[0] for x in FIELD_UI]}
        if 'fields_raw' in st.session_state:
            meta=st.session_state.get('meta',{})
            st.caption('OCR utilizzato: sì' if st.session_state.get('ocr') else 'PDF testuale: OCR non necessario')
            st.subheader('1. Dati estratti e verifica')
            st.caption('Campo vuoto = dato non trovato. Lo zero va inserito soltanto se il valore è realmente zero.')
            cols=st.columns(3); edited={}
            for idx,(key,label,typ) in enumerate(FIELD_UI):
                with cols[idx%3]:
                    default=st.session_state['edit'].get(key,'')
                    val=st.text_input(label,value=default,key=f'edit_{key}')
                    edited[key]=val if typ=='text' else parse_money(val)
                    e=meta.get('evidence',{}).get(key)
                    st.caption(f"Riconoscimento {int(e['confidence']*100)}%" if e else ('Dato non trovato automaticamente' if typ!='text' else ''))
            quality=validate_extraction(edited,meta.get('evidence',{}))
            if quality['reliable']: st.success(f"Qualità dati: ADEGUATA — completezza {quality['completeness']*100:.0f}%")
            else: st.warning(f"Qualità dati: NON ADEGUATA — completezza {quality['completeness']*100:.0f}%")
            for w in quality['warnings']: st.warning(w)
            with st.expander('Evidenze di estrazione'):
                rows=[{'Voce':k,'Confidenza':f"{e['confidence']*100:.0f}%",'Evidenza':e['evidence']} for k,e in meta.get('evidence',{}).items()]
                if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

            st.subheader('2. Valutazioni professionali preliminari')
            q1,q2,q3,q4=st.columns(4); qual={}
            with q1: qual['continuita']=st.slider('Continuità aziendale',1,5,3)
            with q2: qual['ristrutturabilita']=st.slider('Ristrutturabilità debito',1,5,3)
            with q3: qual['asset_strategici']=st.slider('Asset strategici',1,5,3)
            with q4: qual['fattibilita_deal']=st.slider('Fattibilità operazione',1,5,3)
            qual['red_flag']=st.checkbox('Red flag grave / KO preliminare')

            core_ok=quality['reliable']
            confirmed=st.checkbox('Confermo di avere verificato i valori e le eventuali correzioni manuali')
            if not core_ok:
                st.error('Scoring bloccato: i dati essenziali non superano i controlli di qualità. Correggi i valori mancanti/anomali prima di procedere.')
            elif not confirmed:
                st.info('Scoring bloccato fino alla conferma della verifica umana.')
            else:
                sc=score(edited,qual); decision=decision_level(edited,sc,quality,qual['red_flag']); profile=distress_profile(sc); ratios=build_ratios(edited); thesis=build_thesis(edited,sc); checklist=document_checklist(edited,sc)
                st.subheader('3. Scheda decisionale')
                st.markdown(f'<div class="decision">{decision[0]}</div>',unsafe_allow_html=True); st.caption(decision[1])
                m1,m2,m3,m4,m5=st.columns(5); m1.metric('Punteggio Radar',f"{sc['totale']}/100"); m2.metric('Classe',sc['classe']); m3.metric('Tax Turnaround Fit',sc['fit']); m4.metric('Distress composito',f"{sc['composito']}/40"); m5.metric('Profilo crisi',profile)
                a,b=st.columns(2)
                with a:
                    st.markdown('**Elementi di interesse**')
                    for x in thesis[0]: st.write('• '+x)
                with b:
                    st.markdown('**Criticità / red flags**')
                    for x in thesis[1]: st.write('• '+x)
                st.markdown('**Indicatori chiave**')
                rr=[]
                for k,v in ratios.items():
                    if v is None: disp='ND'
                    elif 'margin' in k.lower() or 'ricavi' in k.lower(): disp=f'{v*100:.1f}%'
                    else: disp=f'{v:.2f}x'
                    rr.append({'Indicatore':k,'Valore':disp})
                st.dataframe(pd.DataFrame(rr),use_container_width=True,hide_index=True)
                with st.expander('Checklist documentale per pre-due-diligence',expanded=True):
                    st.dataframe(pd.DataFrame(checklist,columns=['Area','Documento / verifica','Priorità']),use_container_width=True,hide_index=True)

                c1,c2=st.columns(2)
                if c1.button('SALVA NEL PORTAFOGLIO DI SESSIONE',use_container_width=True):
                    item={'data':datetime.datetime.now().isoformat(timespec='minutes'),'societa':edited.get('ragione_sociale') or up.name,'score':sc['totale'],'classe':sc['classe'],'fit':sc['fit'],'decisione':decision[0],'fields':edited,'scoring':sc}
                    st.session_state['portfolio'].append(item); st.success('Target salvato nella sessione. Il PDF non è stato salvato.')
                excel=make_excel(edited,sc,quality,qual,decision,thesis,checklist)
                c2.download_button('ESPORTA SCHEDA EXCEL',excel,file_name=f"Radar_{(edited.get('ragione_sociale') or 'Target').replace(' ','_')}_3.1.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)

with T2:
    p=st.session_state['portfolio']
    if not p: st.info('Nessun target salvato nella sessione corrente.')
    else:
        df=pd.DataFrame([{k:v for k,v in x.items() if k not in ('fields','scoring')} for x in p])
        st.dataframe(df,use_container_width=True,hide_index=True)
        out=io.BytesIO()
        with pd.ExcelWriter(out,engine='openpyxl') as writer: df.to_excel(writer,index=False,sheet_name='PORTAFOGLIO')
        out.seek(0); st.download_button('ESPORTA PORTAFOGLIO',out,'Portafoglio_Radar_3.1.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if st.button('SVUOTA PORTAFOGLIO DI SESSIONE'):
            st.session_state['portfolio']=[]; st.rerun()

with T3:
    st.markdown('''**Controlli attivi nella versione 3.1**

- autenticazione tramite Streamlit Secrets; nessuna password nel codice;
- blocco del caricamento se le credenziali non sono configurate;
- elaborazione del PDF in memoria, senza salvataggio intenzionale del documento nell’app;
- nessun database persistente nella versione pre-produzione: il portafoglio vive solo nella sessione;
- scoring bloccato se i dati essenziali non superano i controlli di qualità;
- verifica umana obbligatoria prima dello scoring;
- separazione tra dato estratto, giudizio professionale e decisione Radar;
- export manuale della scheda e della checklist documentale.

**Non è ancora una piattaforma production-grade per documenti professionali riservati.** Prima dell’uso reale devono essere verificati contratto/condizioni dell’hosting, localizzazione e conservazione dei dati, gestione accessi multiutente, log, backup, data retention e database persistente protetto. La 3.1 serve a validare il prodotto e il processo con documenti fittizi o anonimizzati.''')

st.caption('Strumento di screening preliminare. Non sostituisce due diligence, valutazione legale/fiscale, attestazioni o decisioni di investimento.')
