import datetime
import io
import pandas as pd
import streamlit as st

from radar_engine import extract_pdf_text, extract_fields_with_meta, validate_extraction, it_num, ENGINE_SIGNATURE
from security import require_login, logout_button
from normalization_engine import suggest_adjustments, normalized_metrics, normalization_status, turnaround_plan, diagnostic_summary
from business_plan_engine import project_5y, scenario_grid
from reporting_v4 import make_v4_excel
from azure_storage import configured as azure_configured, upload_bytes, dated_name

VERSION='4.5'
st.set_page_config(page_title="Radar Crisi d'Impresa",page_icon='📊',layout='wide')
st.markdown('''<style>.block-container{max-width:1320px;padding-top:1.3rem}.title{font-size:2.25rem;font-weight:780}.sub{color:#777;margin-bottom:1rem}.decision{font-size:1.25rem;font-weight:750;padding:.7rem 1rem;border-radius:10px;background:#f4f4f4}.small{font-size:.88rem;color:#666}</style>''',unsafe_allow_html=True)
require_login(); logout_button()
st.markdown('<div class="title">Radar Crisi d’Impresa — Turnaround 4.5</div>',unsafe_allow_html=True)
st.markdown('<div class="sub">Evidence-first extraction · Normalization Gate · Business Plan 5Y</div>',unsafe_allow_html=True)
st.caption(f'Engine: {ENGINE_SIGNATURE}')
st.info('Principio 4.5: il business plan è BLOCCATO finché i dati contabili non sono coerenti, le rettifiche materiali non sono chiuse e il professionista non conferma la base normalizzata.')

if 'portfolio42' not in st.session_state: st.session_state.portfolio42=[]

def fmt(v):
    if v is None:return ''
    if isinstance(v,float) and v.is_integer():v=int(v)
    return f'{v:,.0f}'.replace(',','.') if isinstance(v,(int,float)) else str(v)

def parse_money(s):
    s=(s or '').strip(); return None if not s else it_num(s)

FIELDS=[
('ragione_sociale','Ragione sociale','text'),('ricavi_correnti','Ricavi vendite/prestazioni A1 (€)','money'),('valore_produzione','Valore della produzione (€)','money'),('altri_ricavi_proventi','Altri ricavi e proventi (€)','money'),('ebit','EBIT / A-B (€)','money'),('ammortamenti_immateriali','Ammortamenti immateriali (€)','money'),('ammortamenti_materiali','Ammortamenti materiali (€)','money'),('svalutazioni_crediti','Svalutazioni crediti (€)','money'),('ebitda','EBITDA reported ricostruito (€)','money'),('risultato_netto','Risultato netto (€)','money'),('cash_flow_operativo','Cash flow operativo reported (€)','money'),('liquidita','Liquidità (€)','money'),('crediti_totali','Crediti complessivi (€)','money'),('rimanenze','Rimanenze (€)','money'),('debito_finanziario','Debito finanziario (€)','money'),('debiti_tributari','Debiti tributari (€)','money'),('debiti_previdenziali','Debiti previdenziali (€)','money'),('debiti_fornitori','Debiti fornitori (€)','money'),('totale_debiti','Totale debiti (€)','money'),('patrimonio_netto','Patrimonio netto (€)','money'),('attivo_circolante','Attivo circolante (€)','money'),('passivita_correnti','Passività correnti / debiti entro 12 mesi (€)','money'),('oneri_finanziari','Oneri finanziari (€)','money')]

T1,T2,T3,T4=st.tabs(['Analizza & normalizza','Business plan & risanamento','Portafoglio','Metodo & sicurezza'])

with T1:
    up=st.file_uploader('Carica il bilancio PDF',type=['pdf'])
    if up and st.button('1 — ESTRAI E PRE-ANALIZZA',type='primary',use_container_width=True):
        with st.spinner('Lettura del bilancio, OCR dove necessario, controlli di coerenza e ricerca evidence-based delle poste non ricorrenti...'):
            pdf=up.getvalue(); text,used_ocr=extract_pdf_text(pdf,ocr=True)
            fields,meta=extract_fields_with_meta(text)
            suggestions=suggest_adjustments(text,fields)
            st.session_state.update({'pdf42':pdf,'filename42':up.name,'text42':text,'fields42':fields,'meta42':meta,'ocr42':used_ocr,'adjustments42':suggestions,'edit42':{k:(v if k=='ragione_sociale' else fmt(v)) for k,v in fields.items()},'confirm42':False})
    if 'fields42' in st.session_state:
        st.caption('OCR utilizzato: sì — layout contabile ottimizzato' if st.session_state.get('ocr42') else 'PDF testuale: OCR non necessario')
        st.subheader('1. Dati reported — estratti, riconciliati e da validare')
        cols=st.columns(3); edited={}; meta=st.session_state.get('meta42',{}); evidence=meta.get('evidence',{})
        for i,(key,label,typ) in enumerate(FIELDS):
            with cols[i%3]:
                val=st.text_input(label,value=st.session_state['edit42'].get(key,''),key='f42_'+key)
                edited[key]=val if typ=='text' else parse_money(val)
                ev=evidence.get(key)
                if ev:
                    st.caption(f"Riconoscimento {int(ev['confidence']*100)}% · {ev.get('method','')}" )
                    with st.expander('Fonte',expanded=False): st.write(ev.get('evidence',''))
                else: st.caption('Da verificare')
        st.session_state['validated42']=edited
        quality=validate_extraction(edited,evidence); st.session_state['quality42']=quality
        if quality['reliable']:
            st.success(f"Controlli contabili superati — completezza {quality['completeness']*100:.0f}%")
        else:
            st.error(f"ESTRAZIONE NON ANCORA AFFIDABILE — completezza {quality['completeness']*100:.0f}%. Correggere i campi segnalati prima di usare il piano.")
        for w in quality['warnings']: st.warning(w)

        st.subheader('2. Registro rettifiche evidence-based')
        st.caption('La 4.5 non propone rettifiche sulla sola presenza di parole generiche. Serve evidenza di eccezionalità/non ricorrenza e un importo collegabile. Solo VERIFICATA entra nei calcoli; ESCLUSA chiude la proposta senza effetto.')
        base_cols=['stato','materialita','categoria','descrizione','importo','impatto_ricavi','impatto_ebitda','ricorrente','confidenza','pagina','fonte']
        adj=pd.DataFrame(st.session_state.get('adjustments42',[]))
        if adj.empty:
            adj=pd.DataFrame([{'stato':'DA VERIFICARE','materialita':'DA DEFINIRE','categoria':'Altro','descrizione':'','importo':0.0,'impatto_ricavi':0.0,'impatto_ebitda':0.0,'ricorrente':'DA VERIFICARE','confidenza':'MANUALE','pagina':None,'fonte':'Inserimento manuale'}])
        for c in base_cols:
            if c not in adj.columns: adj[c]=None
        adj=adj[base_cols]
        adj=st.data_editor(adj,num_rows='dynamic',use_container_width=True,key='adj42',disabled=['confidenza','pagina','fonte'],column_config={
            'stato':st.column_config.SelectboxColumn(options=['DA VERIFICARE','VERIFICATA','ESCLUSA']),
            'materialita':st.column_config.SelectboxColumn(options=['ALTA','MEDIA','BASSA','DA DEFINIRE']),
            'categoria':st.column_config.SelectboxColumn(options=['Non-core / non recurring','Straordinaria / non recurring','Costo one-off','Normalizzazione gestionale','Altro']),
            'importo':st.column_config.NumberColumn(format='€ %.0f'),'impatto_ricavi':st.column_config.NumberColumn(format='€ %.0f'),'impatto_ebitda':st.column_config.NumberColumn(format='€ %.0f')})
        st.session_state['adjustments42']=adj.to_dict('records')
        nm=normalized_metrics(edited,st.session_state['adjustments42']); st.session_state['nm42']=nm
        c=st.columns(5)
        c[0].metric('EBITDA reported',fmt(nm['ebitda_reported']))
        c[1].metric('Rettifiche EBITDA verificate',fmt(nm['rettifiche_ebitda']))
        c[2].metric('EBITDA normalizzato',fmt(nm['ebitda_normalizzato']))
        c[3].metric('Ricavi operativi normalizzati',fmt(nm['ricavi_operativi_normalizzati']))
        c[4].metric('EBITDA margin norm.',f"{nm['ebitda_margin_normalizzato']*100:.1f}%" if nm['ebitda_margin_normalizzato'] is not None else 'ND')
        if nm['n_rettifiche_materiali_da_verificare']:
            st.error(f"NORMALIZZAZIONE APERTA: {nm['n_rettifiche_materiali_da_verificare']} rettifiche ALTA/MEDIA materialità devono essere VERIFICATE o ESCLUSE.")
        elif nm['n_rettifiche_da_verificare']:
            st.warning(f"Restano {nm['n_rettifiche_da_verificare']} rettifiche a bassa/indefinita materialità da chiudere.")
        with st.expander('Diagnosi preliminare',expanded=True):
            for p in diagnostic_summary(edited,nm): st.write('• '+p)
        confirm=st.checkbox('Confermo professionalmente i dati reported, la riconciliazione contabile e la classificazione delle rettifiche',key='confirm42')
        gate=normalization_status(st.session_state['adjustments42'],quality['reliable'],confirm); st.session_state['gate42']=gate
        if gate['ready']:
            st.success('NORMALIZATION GATE SUPERATO — la base può alimentare il modello prospettico.')
        else:
            st.error('BUSINESS PLAN BLOCCATO — '+('; '.join(gate['reasons']) if gate['reasons'] else 'normalizzazione incompleta'))

with T2:
    if 'validated42' not in st.session_state or 'nm42' not in st.session_state:
        st.info('Prima esegui “Analizza & normalizza”.')
    else:
        d=st.session_state['validated42']; nm=st.session_state['nm42']; q=st.session_state.get('quality42',{'reliable':False})
        gate=normalization_status(st.session_state.get('adjustments42',[]),q.get('reliable',False),st.session_state.get('confirm42',False))
        if not gate['ready']:
            st.error('BUSINESS PLAN BLOCCATO. Torna alla scheda “Analizza & normalizza” e chiudi: '+('; '.join(gate['reasons']) if gate['reasons'] else 'normalizzazione incompleta'))
            st.stop()
        st.subheader('3. Assunzioni di turnaround — riconciliate al core storico')
        hist_margin=nm.get('ebitda_margin_normalizzato')
        st.metric('EBITDA margin storico normalizzato',f'{hist_margin*100:.1f}%' if hist_margin is not None else 'ND')
        st.caption('Nessun margine target è imposto dal software. Il default replica il core normalizzato; ogni miglioramento deve essere modificato consapevolmente e sostenuto da azioni operative.')
        default_margin=max(-0.30,min(0.40,float(hist_margin or 0.0)))
        a,b,c,dcol=st.columns(4)
        with a: growth=st.number_input('Crescita ricavi annua — Base',-0.30,0.50,0.00,0.01,format='%.2f')
        with b: margin_y1=st.number_input('EBITDA margin Y1',-0.30,0.40,default_margin,0.01,format='%.2f')
        with c: margin_y5=st.number_input('EBITDA margin Y5',-0.30,0.40,default_margin,0.01,format='%.2f')
        with dcol: tax_years=st.number_input('Anni rientro fiscale',1,20,10)
        if margin_y5>default_margin+0.005:
            st.warning('Il miglioramento di marginalità deve essere supportato da un action bridge quantificato (pricing, volumi, organico, costi, dismissioni).')
        action_bridge=st.text_area('Action bridge operativo a supporto del margine target',placeholder='Esempio: +€X pricing; +€Y nuovi contratti; -€Z costo personale; -€W servizi; tempistica e responsabili.')
        a,b,c,dcol=st.columns(4)
        with a: haircut=st.number_input('Riduzione debito fiscale/previdenziale — scenario economico',0.00,0.80,0.00,0.05,format='%.2f')
        with b: dso=st.number_input('DSO target giorni',0,365,75)
        with c: dio=st.number_input('DIO/SAL target giorni',0,365,30)
        with dcol: dpo=st.number_input('DPO target giorni',0,365,100)
        a,b,c,dcol=st.columns(4)
        with a: cash_cost_ratio=st.number_input('Costi cash operativi / ricavi per proxy CCN',0.00,1.50,0.30,0.05,format='%.2f')
        with b: capex=st.number_input('Capex annuo (€)',0.0,100000000.0,0.0,10000.0)
        with c: fin_service=st.number_input('Servizio annuo debito finanziario (€)',0.0,100000000.0,0.0,10000.0)
        with dcol: supplier_service=st.number_input('Rientro annuo arretrati fornitori (€)',0.0,100000000.0,0.0,10000.0)
        margins=[margin_y1+(margin_y5-margin_y1)*i/4 for i in range(5)]
        ass={'growth':[growth]*5,'margin':margins,'falcidia_fiscale':haircut,'anni_fisco':tax_years,'dso':[dso]*5,'dio':[dio]*5,'dpo':[dpo]*5,'cash_cost_ratio':[cash_cost_ratio]*5,'capex':[capex]*5,'servizio_finanziario_annuo':fin_service,'rientro_fornitori_annuo':supplier_service,'tax_rate':0.0,'action_bridge':action_bridge}
        plan=project_5y(d,nm,ass); scenarios=scenario_grid(d,nm,ass); actions=turnaround_plan(d,nm,ass); diag=diagnostic_summary(d,nm)
        st.subheader('4. Business plan 5 anni — Base')
        st.dataframe(pd.DataFrame(plan),use_container_width=True,hide_index=True)
        st.subheader('5. Stress test')
        st.dataframe(pd.DataFrame(scenarios),use_container_width=True,hide_index=True)
        st.subheader('6. Piano analitico di risanamento')
        st.dataframe(pd.DataFrame(actions,columns=['Area','Azione','Priorità','KPI','Target / trigger']),use_container_width=True,hide_index=True)
        if any(x['dscr'] is not None and x['dscr']<1 for x in plan): st.error('Il Base presenta almeno un anno con DSCR < 1,0x: il debt service non è coperto dal CFADS ipotizzato.')
        elif all(x['dscr'] is None or x['dscr']>=1 for x in plan): st.success('Nel Base non emergono anni con DSCR < 1,0x. La conclusione vale esclusivamente per le assunzioni inserite e validate.')
        report=make_v4_excel(d,nm,st.session_state.get('adjustments42',[]),plan,actions,scenarios,diag,gate=gate,assumptions=ass)
        filename=f"Radar_Turnaround_{(d.get('ragione_sociale') or 'Target').replace(' ','_')}_4.5.xlsx"
        st.download_button('ESPORTA REPORT TURNAROUND 4.5',report,filename,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        if st.button('SALVA TARGET NEL PORTAFOGLIO DI SESSIONE',use_container_width=True):
            st.session_state.portfolio42.append({'data':datetime.datetime.now().isoformat(timespec='minutes'),'societa':d.get('ragione_sociale'),'ebitda_reported':nm.get('ebitda_reported'),'ebitda_normalizzato':nm.get('ebitda_normalizzato'),'cfo':d.get('cash_flow_operativo'),'rettifiche_verificate':nm.get('n_rettifiche_verificate')}); st.success('Salvato nella sessione.')
        if azure_configured():
            if st.button('ARCHIVIA REPORT SU AZURE',use_container_width=True):
                ok,msg=upload_bytes(dated_name('reports',filename),report,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                (st.success if ok else st.error)(msg)
        else:
            st.caption('Archiviazione Azure opzionale non configurata. Per abilitarla: secret AZURE_CONTAINER_SAS_URL limitato al container privato.')

with T3:
    if not st.session_state.portfolio42: st.info('Nessun target nella sessione corrente.')
    else:
        df=pd.DataFrame(st.session_state.portfolio42); st.dataframe(df,use_container_width=True,hide_index=True)
        out=io.BytesIO(); df.to_excel(out,index=False); out.seek(0); st.download_button('ESPORTA PORTAFOGLIO',out,'Portafoglio_Radar_4.4.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

with T4:
    st.markdown('''**Architettura 4.5**

1. OCR ottimizzato per tabelle contabili e parsing page-aware.
2. Estrazione prioritaria dai prospetti di bilancio; la Nota integrativa è usata come cross-check/rescue, non come sorgente indiscriminata di numeri.
3. Controlli di coerenza contabile: i totali devono essere compatibili con le componenti e i numeri sospetti bloccano il modello.
4. Rettifiche evidence-based: servono importo + evidenza esplicita di eccezionalità/non ricorrenza; niente keyword harvesting generico.
5. Solo VERIFICATA modifica il bridge; ESCLUSA chiude la proposta senza impatto.
6. **Normalization Gate**: il BP resta bloccato con estrazione incoerente, rettifiche materiali pendenti o mancata conferma professionale.
7. EBITDA = EBIT + ammortamenti immateriali + materiali; svalutazioni crediti non automaticamente add-back.
8. Forecast ancorato al margine core normalizzato: nessun 8% preimpostato. Gli uplift devono essere supportati da action bridge.
9. Business plan 5Y: CCN, CFADS, debt service, DSCR, stress test e piano di risanamento.

**Sicurezza:** login tramite Streamlit Secrets; PDF elaborato in memoria. Azure opzionale tramite SAS limitato al container privato; nessuna credenziale nel repository.''')

st.caption('Strumento di screening e modellazione preliminare. Non sostituisce due diligence, attestazioni, valutazioni legali/fiscali o giudizi professionali sulla fattibilità del piano.')
