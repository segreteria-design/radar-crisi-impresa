import datetime
import io
import pandas as pd
import streamlit as st

from radar_engine import extract_pdf_text, extract_fields_with_meta, validate_extraction, it_num
from security import require_login, logout_button
from normalization_engine import suggest_adjustments, normalized_metrics, turnaround_plan, diagnostic_summary
from business_plan_engine import project_5y, scenario_grid
from reporting_v4 import make_v4_excel
from azure_storage import configured as azure_configured, upload_bytes, dated_name

VERSION='4.1'
st.set_page_config(page_title="Radar Crisi d'Impresa",page_icon='📊',layout='wide')
st.markdown('''<style>.block-container{max-width:1320px;padding-top:1.3rem}.title{font-size:2.25rem;font-weight:780}.sub{color:#777;margin-bottom:1rem}.decision{font-size:1.25rem;font-weight:750;padding:.7rem 1rem;border-radius:10px;background:#f4f4f4}.small{font-size:.88rem;color:#666}</style>''',unsafe_allow_html=True)
require_login(); logout_button()
st.markdown('<div class="title">Radar Crisi d’Impresa — Turnaround 4.1</div>',unsafe_allow_html=True)
st.markdown('<div class="sub">Normalization Engine · Cash & Distress Diagnostics · Business Plan 5Y</div>',unsafe_allow_html=True)
st.info('Principio 4.1: nessun indice di turnaround viene considerato definitivo prima della normalizzazione. Solo le rettifiche marcate VERIFICATA entrano nei KPI e nel business plan.')

if 'portfolio41' not in st.session_state: st.session_state.portfolio41=[]

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
        with st.spinner('Lettura del bilancio, OCR dove necessario e ricerca di poste non ricorrenti...'):
            pdf=up.getvalue(); text,used_ocr=extract_pdf_text(pdf,ocr=True)
            fields,meta=extract_fields_with_meta(text)
            suggestions=suggest_adjustments(text)
            st.session_state.update({'pdf41':pdf,'filename41':up.name,'text41':text,'fields41':fields,'meta41':meta,'ocr41':used_ocr,'adjustments41':suggestions,'edit41':{k:(v if k=='ragione_sociale' else fmt(v)) for k,v in fields.items()}})
    if 'fields41' in st.session_state:
        st.caption('OCR utilizzato: sì' if st.session_state.get('ocr41') else 'PDF testuale: OCR non necessario')
        st.subheader('1. Dati reported — estratti e da validare')
        cols=st.columns(3); edited={}; meta=st.session_state.get('meta41',{}); evidence=meta.get('evidence',{})
        for i,(key,label,typ) in enumerate(FIELDS):
            with cols[i%3]:
                val=st.text_input(label,value=st.session_state['edit41'].get(key,''),key='f41_'+key)
                edited[key]=val if typ=='text' else parse_money(val)
                ev=evidence.get(key); st.caption(f"Riconoscimento {int(ev['confidence']*100)}%" if ev else 'Da verificare')
        st.session_state['validated41']=edited
        quality=validate_extraction(edited,evidence)
        (st.success if quality['reliable'] else st.warning)(f"Completezza tecnica {quality['completeness']*100:.0f}% — {'adeguata per proseguire con verifica umana' if quality['reliable'] else 'integrare i dati mancanti'}")
        for w in quality['warnings']: st.warning(w)

        st.subheader('2. Registro rettifiche — il cuore del nuovo motore')
        st.caption('Importo = valore della posta. Impatto ricavi/EBITDA = rettifica con segno: per eliminare un ricavo non recurring di €3 mln inserire -3.000.000. Nessuna riga incide finché Stato ≠ VERIFICATA.')
        base_cols=['stato','categoria','descrizione','importo','impatto_ricavi','impatto_ebitda','ricorrente','confidenza']
        adj=pd.DataFrame(st.session_state.get('adjustments41',[]),columns=base_cols)
        if adj.empty: adj=pd.DataFrame([{'stato':'DA VERIFICARE','categoria':'One-off','descrizione':'','importo':0.0,'impatto_ricavi':0.0,'impatto_ebitda':0.0,'ricorrente':'DA VERIFICARE','confidenza':'MANUALE'}])
        adj=st.data_editor(adj,num_rows='dynamic',use_container_width=True,key='adj41',column_config={
            'stato':st.column_config.SelectboxColumn(options=['SUGGERITA','DA VERIFICARE','VERIFICATA','ESCLUSA']),
            'categoria':st.column_config.SelectboxColumn(options=['Straordinaria','Non-core','Normalizzazione gestionale','Potenziale one-off','Altro']),
            'importo':st.column_config.NumberColumn(format='€ %.0f'),'impatto_ricavi':st.column_config.NumberColumn(format='€ %.0f'),'impatto_ebitda':st.column_config.NumberColumn(format='€ %.0f')})
        st.session_state['adjustments41']=adj.to_dict('records')
        nm=normalized_metrics(edited,st.session_state['adjustments41']); st.session_state['nm41']=nm
        c=st.columns(5)
        c[0].metric('EBITDA reported',fmt(nm['ebitda_reported']))
        c[1].metric('Rettifiche EBITDA',fmt(nm['rettifiche_ebitda']))
        c[2].metric('EBITDA normalizzato',fmt(nm['ebitda_normalizzato']))
        c[3].metric('Ricavi operativi normalizzati',fmt(nm['ricavi_operativi_normalizzati']))
        c[4].metric('EBITDA margin norm.',f"{nm['ebitda_margin_normalizzato']*100:.1f}%" if nm['ebitda_margin_normalizzato'] is not None else 'ND')
        if nm['n_rettifiche_da_verificare']:
            st.warning(f"Restano {nm['n_rettifiche_da_verificare']} rettifiche non verificate: gli output sono provvisori.")
        with st.expander('Diagnosi preliminare',expanded=True):
            for p in diagnostic_summary(edited,nm): st.write('• '+p)
        if st.checkbox('Confermo la verifica professionale dei dati reported e delle rettifiche inserite',key='confirm41'):
            st.success('Base normalizzata validata per il modello prospettico.')
        else:
            st.info('Il business plan resta utilizzabile come simulazione, ma il report segnalerà che la normalizzazione non è stata confermata.')

with T2:
    if 'validated41' not in st.session_state or 'nm41' not in st.session_state:
        st.info('Prima esegui “Analizza & normalizza”.')
    else:
        d=st.session_state['validated41']; nm=st.session_state['nm41']
        st.subheader('3. Assunzioni di turnaround')
        st.caption('Le assunzioni sono modificabili e devono essere corroborate da dati commerciali, operativi e finanziari. Non sono previsioni automatiche.')
        a,b,c,dcol=st.columns(4)
        with a: growth=st.number_input('Crescita ricavi annua — Base',-0.30,0.50,0.05,0.01,format='%.2f')
        with b: margin=st.number_input('EBITDA margin target — Base',-0.30,0.40,0.08,0.01,format='%.2f')
        with c: haircut=st.number_input('Riduzione debito fiscale/previdenziale — scenario economico',0.00,0.80,0.00,0.05,format='%.2f')
        with dcol: tax_years=st.number_input('Anni rientro fiscale',1,20,10)
        a,b,c,dcol=st.columns(4)
        with a: dso=st.number_input('DSO target giorni',0,365,75)
        with b: dio=st.number_input('DIO/SAL target giorni',0,365,30)
        with c: dpo=st.number_input('DPO target giorni',0,365,100)
        with dcol: cash_cost_ratio=st.number_input('Costi cash operativi / ricavi per proxy CCN',0.00,1.50,0.30,0.05,format='%.2f')
        a,b,c=st.columns(3)
        with a: capex=st.number_input('Capex annuo (€)',0.0,100000000.0,50000.0,10000.0)
        with b: fin_service=st.number_input('Servizio annuo debito finanziario (€)',0.0,100000000.0,0.0,10000.0)
        with c: supplier_service=st.number_input('Rientro annuo arretrati fornitori (€)',0.0,100000000.0,0.0,10000.0)
        ass={'growth':[growth]*5,'margin':[margin]*5,'falcidia_fiscale':haircut,'anni_fisco':tax_years,'dso':[dso]*5,'dio':[dio]*5,'dpo':[dpo]*5,'cash_cost_ratio':[cash_cost_ratio]*5,'capex':[capex]*5,'servizio_finanziario_annuo':fin_service,'rientro_fornitori_annuo':supplier_service,'tax_rate':0.0}
        plan=project_5y(d,nm,ass); scenarios=scenario_grid(d,nm,ass); actions=turnaround_plan(d,nm,ass); diag=diagnostic_summary(d,nm)
        st.subheader('4. Business plan 5 anni — Base')
        pdf=pd.DataFrame(plan); st.dataframe(pdf,use_container_width=True,hide_index=True)
        st.subheader('5. Stress test')
        st.dataframe(pd.DataFrame(scenarios),use_container_width=True,hide_index=True)
        st.subheader('6. Piano analitico di risanamento')
        st.dataframe(pd.DataFrame(actions,columns=['Area','Azione','Priorità','KPI','Target / trigger']),use_container_width=True,hide_index=True)
        if any(x['dscr'] is not None and x['dscr']<1 for x in plan): st.error('Il piano Base presenta almeno un anno con DSCR < 1,0x: il servizio del debito non è coperto dal CFADS ipotizzato.')
        elif all(x['dscr'] is None or x['dscr']>=1 for x in plan): st.success('Nel Base non emergono anni con DSCR < 1,0x, fermo restando che le assunzioni devono essere validate.')
        report=make_v4_excel(d,nm,st.session_state.get('adjustments41',[]),plan,actions,scenarios,diag)
        filename=f"Radar_Turnaround_{(d.get('ragione_sociale') or 'Target').replace(' ','_')}_4.1.xlsx"
        st.download_button('ESPORTA REPORT TURNAROUND 4.1',report,filename,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
        if st.button('SALVA TARGET NEL PORTAFOGLIO DI SESSIONE',use_container_width=True):
            st.session_state.portfolio41.append({'data':datetime.datetime.now().isoformat(timespec='minutes'),'societa':d.get('ragione_sociale'),'ebitda_reported':nm.get('ebitda_reported'),'ebitda_normalizzato':nm.get('ebitda_normalizzato'),'cfo':d.get('cash_flow_operativo'),'rettifiche_verificate':nm.get('n_rettifiche_verificate')}); st.success('Salvato nella sessione.')
        if azure_configured():
            if st.button('ARCHIVIA REPORT SU AZURE',use_container_width=True):
                ok,msg=upload_bytes(dated_name('reports',filename),report,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                (st.success if ok else st.error)(msg)
        else:
            st.caption('Archiviazione Azure opzionale non configurata. Per abilitarla: secret AZURE_CONTAINER_SAS_URL limitato al container privato.')

with T3:
    if not st.session_state.portfolio41: st.info('Nessun target nella sessione corrente.')
    else:
        df=pd.DataFrame(st.session_state.portfolio41); st.dataframe(df,use_container_width=True,hide_index=True)
        out=io.BytesIO(); df.to_excel(out,index=False); out.seek(0); st.download_button('ESPORTA PORTAFOGLIO',out,'Portafoglio_Radar_4.1.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

with T4:
    st.markdown('''**Architettura 4.1**

1. Estrazione del bilancio con evidenza e controllo qualità.
2. Separazione tra ricavi/costi reported e rettifiche di normalizzazione.
3. Nessuna rettifica entra nel modello finché il professionista non la marca **VERIFICATA**.
4. EBITDA ricostruito come EBIT + ammortamenti immateriali + materiali; le svalutazioni crediti non sono automaticamente aggiunte indietro.
5. Ricavi operativi normalizzati: valore della produzione, ove disponibile, rettificato delle componenti non ricorrenti verificate.
6. Cash flow operativo reported utilizzato come controllo indipendente della qualità dell'utile.
7. Business plan 5 anni con capitale circolante, CFADS, servizio del debito, DSCR e stress test.
8. Piano di risanamento analitico con azioni, priorità, KPI e trigger.

**Sicurezza:** login tramite Streamlit Secrets; PDF elaborato in memoria. Azure è opzionale e può essere collegato tramite un SAS limitato al container privato; nessuna credenziale deve essere inserita nel repository.''')

st.caption('Strumento di screening e modellazione preliminare. Non sostituisce due diligence, attestazioni, valutazioni legali/fiscali o giudizi professionali sulla fattibilità del piano.')
