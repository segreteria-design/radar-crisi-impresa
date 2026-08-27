import re
from radar_engine import it_num

KEYWORDS = {
    'Straordinaria': ['sopravvenienz','minusvalenz','plusvalenz','straordinar','risarciment','una tantum'],
    'Non-core': ['intermediazione','cessione immobile','cessione partecipaz','non ripetibile','non ricorrente','occasionale'],
    'Normalizzazione gestionale': ['compenso amministratore','parti correlate','socio','correlata'],
    'Potenziale one-off': ['consulenza legale','penale','multa','ammenda','contenzioso','ristrutturazione']
}
NUM = r"\d{1,3}(?:[\.,]\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def _amounts(s):
    out=[]
    for x in re.findall(NUM,s or ''):
        v=it_num(x)
        if v is not None and abs(v)>=1000: out.append(abs(v))
    return out


def suggest_adjustments(text_or_lines):
    lines=text_or_lines.splitlines() if isinstance(text_or_lines,str) else list(text_or_lines)
    clean=[re.sub(r'\s+',' ',x).strip() for x in lines if str(x).strip()]
    out=[]; seen=set()
    for i,line in enumerate(clean):
        ctx=' '.join(clean[max(0,i-2):min(len(clean),i+3)])
        low=ctx.lower()
        for category,kws in KEYWORDS.items():
            if not any(k in low for k in kws): continue
            amounts=_amounts(ctx)
            explicit=re.search(r'(?:ricavo|provento|operazione)[^\n]{0,100}?(?:euro|€)\s*('+NUM+r')',ctx,re.I)
            amount=it_num(explicit.group(1)) if explicit else (max(amounts) if amounts else None)
            # Strong automatic proposal only where the note explicitly states non-repeatability/non-recurring nature.
            strong=('non ripetib' in low or 'non ricorrent' in low or 'una tantum' in low)
            impact=-amount if (amount is not None and strong and any(k in low for k in ['ricavo','provento','intermediazione','plusvalenza'])) else 0.0
            key=(category,round(amount or 0,2),ctx[:120])
            if key in seen: continue
            seen.add(key)
            out.append({
                'descrizione':ctx[:300], 'categoria':category, 'importo':amount,
                'impatto_ricavi':impact if strong else 0.0,
                'impatto_ebitda':impact if strong else 0.0,
                'ricorrente':'NO' if strong else 'DA VERIFICARE',
                'stato':'SUGGERITA', 'confidenza':'ALTA' if strong else 'MEDIA'
            })
    # Deduplicate near-identical 3m intermediation suggestion generated across adjacent OCR lines.
    final=[]
    for a in out:
        duplicate=False
        for b in final:
            if a['categoria']==b['categoria'] and a.get('importo') and b.get('importo') and abs(a['importo']-b['importo'])<1 and ('intermediazione' in a['descrizione'].lower())==('intermediazione' in b['descrizione'].lower()):
                duplicate=True; break
        if not duplicate: final.append(a)
    return final[:20]


def normalized_metrics(d,adjustments):
    verified=[a for a in adjustments if str(a.get('stato','')).strip().upper()=='VERIFICATA']
    adj_ebitda=sum(float(a.get('impatto_ebitda') or 0) for a in verified)
    adj_rev=sum(float(a.get('impatto_ricavi') or 0) for a in verified)
    e_rep=d.get('ebitda'); vp=d.get('valore_produzione')
    # Operating revenue base: value of production if available, otherwise sales revenue.
    op_rev_rep=vp if vp is not None else d.get('ricavi_correnti')
    e_norm=(e_rep+adj_ebitda) if e_rep is not None else None
    op_rev_norm=(op_rev_rep+adj_rev) if op_rev_rep is not None else None
    fin=d.get('debito_finanziario'); cash=d.get('liquidita')
    pfn=(fin or 0)-(cash or 0) if (fin is not None or cash is not None) else None
    total_fin_pressure=(d.get('debito_finanziario') or 0)+(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    return {
        'ricavi_vendite_reported':d.get('ricavi_correnti'), 'ricavi_operativi_reported':op_rev_rep,
        'rettifiche_ricavi':adj_rev, 'ricavi_operativi_normalizzati':op_rev_norm,
        'ebitda_reported':e_rep,'rettifiche_ebitda':adj_ebitda,'ebitda_normalizzato':e_norm,
        'ebitda_margin_normalizzato':e_norm/op_rev_norm if op_rev_norm and e_norm is not None else None,
        'pfn':pfn,'pfn_ebitda_normalizzato':pfn/e_norm if e_norm and e_norm>0 and pfn is not None else None,
        'pressione_finanziaria_fiscale':total_fin_pressure,
        'n_rettifiche_verificate':len(verified),'n_rettifiche_da_verificare':sum(1 for a in adjustments if str(a.get('stato','')).upper()!='VERIFICATA')
    }


def turnaround_plan(d,nm,assumptions=None):
    assumptions=assumptions or {}; actions=[]
    rev=nm.get('ricavi_operativi_normalizzati') or d.get('ricavi_correnti') or 0
    e=nm.get('ebitda_normalizzato'); tax=(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    suppliers=d.get('debiti_fornitori') or 0; cfo=d.get('cash_flow_operativo')
    if nm.get('n_rettifiche_da_verificare'):
        actions.append(('Normalizzazione','Documentare e validare tutte le rettifiche materiali prima di assumere decisioni sul piano.','IMMEDIATA','Bridge EBITDA verificato','100% poste materiali documentate'))
    if e is None:
        actions.append(('Dati','Ricostruire EBITDA normalizzato prima di formulare la tesi di risanamento.','IMMEDIATA','EBITDA normalized','Disponibile e riconciliato'))
    elif e<=0:
        actions.append(('Industriale','Turnaround operativo necessario: il solo intervento sul passivo non rende sostenibile il core business.','IMMEDIATA','EBITDA core','> 0 e progressione verso target'))
    elif rev and e/rev<.08:
        actions.append(('Marginalità','Piano prezzi/costi per portare il margine core in area compatibile con il settore e con il debt service.','ALTA','EBITDA margin','Target da validare per settore'))
    if cfo is not None and cfo<0:
        actions.append(('Tesoreria','Attivare 13-week cash flow con riconciliazione settimanale e waterfall dei pagamenti.','IMMEDIATA','Minimum cash','Nessun liquidity gap non coperto'))
    if tax and rev and tax/rev>.20:
        actions.append(('Fiscale/previdenziale','Riconciliare scaduto, ruoli, rateazioni e contenzioso; modellare trattamento e servizio del debito per scenario.','ALTA','Debito fiscale/previdenziale','Cash schedule sostenibile'))
    if suppliers and rev and suppliers/rev>.20:
        actions.append(('Fornitori','Ageing e segmentazione fornitori strategici/non strategici; accordi e standstill coerenti con continuità.','ALTA','DPO/arretrati','Nessun blocco attività core'))
    if d.get('crediti_totali') and rev and d['crediti_totali']>rev*1.5:
        actions.append(('Crediti','Ageing, conferme saldi, verifica parti correlate e probabilità di incasso; non usare il nominale come cassa disponibile.','IMMEDIATA','Cash conversion','Piano incassi documentato'))
    actions.append(('Governance','Reporting mensile actual-vs-plan, covenant interni, trigger e azioni correttive.','MEDIA','Closing/reporting','Entro 10 giorni dal mese'))
    return actions


def diagnostic_summary(d,nm):
    e=nm.get('ebitda_normalizzato'); cfo=d.get('cash_flow_operativo'); points=[]
    if e is not None and e<0: points.append('Il core business risulta in perdita dopo le rettifiche verificate.')
    if cfo is not None and cfo<0: points.append('La gestione operativa assorbe cassa nonostante il risultato civilistico.')
    if (d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)>0: points.append('Il passivo fiscale/previdenziale deve essere modellato per scadenza e trattamento, non come aggregato.')
    if d.get('debiti_fornitori'): points.append('Il debito fornitori richiede ageing e segmentazione per impatto sulla continuità.')
    if not points: points.append('Nessuna conclusione robusta senza validazione delle rettifiche e del cash flow prospettico.')
    return points
