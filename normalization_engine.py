import re
from radar_engine import it_num, NUM_RE

# 4.2 deliberately avoids generic keyword harvesting. A normalization proposal must be tied
# to evidence that indicates exceptional/non-recurring/non-core nature and to an amount.
STRONG_TRIGGERS = [
    'non ripetibile','non ricorrente','una tantum','evento eccezionale','incidenza eccezionale',
    'entità eccezionale','entita eccezionale','straordinario','straordinaria','eccezionale',
]
NONCORE_TRIGGERS = ['intermediazione','cessione di quote','cessione partecipaz','cessione immobile','plusvalenza','minusvalenza']
COST_TRIGGERS = ['penale','multa','ammenda','risarcimento','contenzioso','costi di ristrutturazione','consulenza straordinaria']


def _norm(s):
    return re.sub(r'\s+',' ',(s or '')).strip()


def _page_blocks(text):
    matches=list(re.finditer(r'--- PAGINA\s+(\d+)\s+---',text or '',flags=re.I))
    if not matches:return [(0,text or '')]
    out=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        out.append((int(m.group(1)),text[m.end():end]))
    return out


def _amount_near(context):
    # Prefer formulations that explicitly tie an amount to a ricavo/costo/evento.
    patterns=[
        r'(?:per\s+l[’\']?importo\s+di|per\s+un\s+importo\s+di|pari\s+ad?|per\s+euro|euro|€)\s*('+NUM_RE+r')',
        r'(?:ricavo|provento|costo|onere)[^\n]{0,120}?('+NUM_RE+r')',
    ]
    vals=[]
    for pat in patterns:
        for m in re.finditer(pat,context,re.I):
            v=it_num(m.group(1))
            if v is not None and abs(v)>=1000: vals.append(abs(v))
    return max(vals) if vals else None


def _materiality(amount, base):
    if not amount:return 'BASSA'
    if not base or base<=0:return 'ALTA' if amount>=250000 else 'MEDIA'
    r=abs(amount)/abs(base)
    if r>=.10:return 'ALTA'
    if r>=.03:return 'MEDIA'
    return 'BASSA'


def suggest_adjustments(text_or_lines, reported=None):
    """Return only evidence-based proposals. No generic matches on 'socio', 'intermediazione bancaria', etc."""
    text='\n'.join(text_or_lines) if not isinstance(text_or_lines,str) else text_or_lines
    reported=reported or {}
    base=reported.get('valore_produzione') or reported.get('ricavi_correnti') or 0
    out=[]; seen=[]
    for page,chunk in _page_blocks(text):
        lines=[_norm(x) for x in chunk.splitlines() if _norm(x)]
        for i,line in enumerate(lines):
            ctx=' '.join(lines[max(0,i-3):min(len(lines),i+5)])
            low=ctx.lower()
            strong=any(t in low for t in STRONG_TRIGGERS)
            noncore=any(t in low for t in NONCORE_TRIGGERS)
            cost=any(t in low for t in COST_TRIGGERS)
            # A proposal requires explicit exceptional/non-repeatability evidence. A non-core keyword alone is insufficient.
            if not strong:
                continue
            amount=_amount_near(ctx)
            if amount is None:
                continue
            if noncore:
                category='Non-core / non recurring'
            elif cost:
                category='Costo one-off'
            else:
                category='Straordinaria / non recurring'
            is_revenue=any(x in low for x in ['ricavo','provento','intermediazione','plusvalenza'])
            is_cost=any(x in low for x in ['costo','onere','penale','multa','ammenda','risarcimento','minusvalenza'])
            # Removing a non-recurring revenue lowers revenue and EBITDA. Removing a one-off cost increases EBITDA.
            impact_rev=-amount if is_revenue else 0.0
            impact_ebitda=-amount if is_revenue else (amount if is_cost else 0.0)
            signature=(round(amount,2), category, page)
            if any(abs(amount-x[0])<1 and category==x[1] and abs(page-x[2])<=1 for x in seen):
                continue
            seen.append(signature)
            out.append({
                'stato':'DA VERIFICARE',
                'categoria':category,
                'descrizione':ctx[:520],
                'importo':amount,
                'impatto_ricavi':impact_rev,
                'impatto_ebitda':impact_ebitda,
                'ricorrente':'NO',
                'confidenza':'ALTA',
                'materialita':_materiality(amount,base),
                'pagina':page,
                'fonte':'Nota integrativa / evidenza testuale',
            })
    out.sort(key=lambda a: (0 if a['materialita']=='ALTA' else 1, -(a.get('importo') or 0)))
    return out[:12]


def normalization_status(adjustments, extraction_reliable=True, professional_confirmed=False):
    pending_material=[a for a in adjustments if str(a.get('stato','')).upper() not in ('VERIFICATA','ESCLUSA') and str(a.get('materialita','')).upper() in ('ALTA','MEDIA')]
    verified=[a for a in adjustments if str(a.get('stato','')).upper()=='VERIFICATA']
    ready=bool(extraction_reliable and professional_confirmed and not pending_material)
    reasons=[]
    if not extraction_reliable: reasons.append('estrazione contabile non validata/coerente')
    if pending_material: reasons.append(f'{len(pending_material)} rettifiche materiali ancora da verificare')
    if not professional_confirmed: reasons.append('manca la conferma professionale finale')
    return {'ready':ready,'reasons':reasons,'pending_material':pending_material,'verified':verified}


def normalized_metrics(d,adjustments):
    verified=[a for a in adjustments if str(a.get('stato','')).strip().upper()=='VERIFICATA']
    pending=[a for a in adjustments if str(a.get('stato','')).strip().upper() not in ('VERIFICATA','ESCLUSA')]
    pending_material=[a for a in pending if str(a.get('materialita','')).upper() in ('ALTA','MEDIA')]
    adj_ebitda=sum(float(a.get('impatto_ebitda') or 0) for a in verified)
    adj_rev=sum(float(a.get('impatto_ricavi') or 0) for a in verified)
    e_rep=d.get('ebitda'); vp=d.get('valore_produzione')
    op_rev_rep=vp if vp is not None else d.get('ricavi_correnti')
    e_norm=(e_rep+adj_ebitda) if e_rep is not None else None
    op_rev_norm=(op_rev_rep+adj_rev) if op_rev_rep is not None else None
    fin=d.get('debito_finanziario'); cash=d.get('liquidita')
    pfn=(fin or 0)-(cash or 0) if (fin is not None or cash is not None) else None
    total_fin_pressure=(d.get('debito_finanziario') or 0)+(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    return {
        'ricavi_vendite_reported':d.get('ricavi_correnti'),'ricavi_operativi_reported':op_rev_rep,
        'rettifiche_ricavi':adj_rev,'ricavi_operativi_normalizzati':op_rev_norm,
        'ebitda_reported':e_rep,'rettifiche_ebitda':adj_ebitda,'ebitda_normalizzato':e_norm,
        'ebitda_margin_normalizzato':e_norm/op_rev_norm if op_rev_norm and e_norm is not None else None,
        'pfn':pfn,'pfn_ebitda_normalizzato':pfn/e_norm if e_norm and e_norm>0 and pfn is not None else None,
        'pressione_finanziaria_fiscale':total_fin_pressure,
        'n_rettifiche_verificate':len(verified),'n_rettifiche_da_verificare':len(pending),
        'n_rettifiche_materiali_da_verificare':len(pending_material),
        'rettifiche_materiali_da_verificare':pending_material,
    }


def turnaround_plan(d,nm,assumptions=None):
    assumptions=assumptions or {}; actions=[]
    rev=nm.get('ricavi_operativi_normalizzati') or d.get('ricavi_correnti') or 0
    e=nm.get('ebitda_normalizzato'); tax=(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    suppliers=d.get('debiti_fornitori') or 0; cfo=d.get('cash_flow_operativo')
    if nm.get('n_rettifiche_materiali_da_verificare'):
        actions.append(('Normalizzazione','Chiudere il bridge delle poste materiali e collegare ogni rettifica alla fonte documentale.','IMMEDIATA','Bridge EBITDA','0 poste materiali pendenti'))
    if e is None:
        actions.append(('Dati','Ricostruire EBITDA normalizzato prima di formulare la tesi di risanamento.','IMMEDIATA','EBITDA normalized','Disponibile e riconciliato'))
    elif e<=0:
        actions.append(('Industriale','Core EBITDA negativo: costruire un bridge operativo per ricavi, pricing, organico e costi prima di intervenire sul solo passivo.','IMMEDIATA','EBITDA core','Break-even operativo documentato'))
    elif rev and e/rev<.08:
        actions.append(('Marginalità','Definire azioni di pricing/costi con impatto quantificato; vietato assumere un margine target non riconciliato.','ALTA','EBITDA margin','Target supportato da action bridge'))
    if cfo is not None and cfo<0:
        actions.append(('Tesoreria','Attivare 13-week cash flow con riconciliazione settimanale e waterfall dei pagamenti.','IMMEDIATA','Minimum cash','Nessun liquidity gap non coperto'))
    if tax and rev and tax/rev>.20:
        actions.append(('Fiscale/previdenziale','Riconciliare scaduto, ruoli, rateazioni e contenzioso; modellare trattamento e servizio del debito per scenario.','ALTA','Debito fiscale/previdenziale','Cash schedule sostenibile'))
    if suppliers and rev and suppliers/rev>.20:
        actions.append(('Fornitori','Ageing e segmentazione fornitori strategici/non strategici; accordi e standstill coerenti con continuità.','ALTA','DPO/arretrati','Nessun blocco attività core'))
    if d.get('crediti_totali') and rev and d['crediti_totali']>rev*1.5:
        actions.append(('Crediti','Ageing, conferme saldi, verifica parti correlate e probabilità di incasso; separare nominale, collectible e cash timing.','IMMEDIATA','Cash conversion','Piano incassi documentato'))
    actions.append(('Governance','Reporting mensile actual-vs-plan, covenant interni, trigger e azioni correttive.','MEDIA','Closing/reporting','Entro 10 giorni dal mese'))
    return actions


def diagnostic_summary(d,nm):
    e=nm.get('ebitda_normalizzato'); cfo=d.get('cash_flow_operativo'); points=[]
    if nm.get('n_rettifiche_materiali_da_verificare'):
        points.append('La normalizzazione non è chiusa: gli indici prospettici non devono essere utilizzati come base decisionale.')
    if e is not None and e<0: points.append('Il core business risulta in perdita dopo le rettifiche verificate.')
    if cfo is not None and cfo<0: points.append('La gestione operativa assorbe cassa nonostante il risultato civilistico.')
    if (d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)>0: points.append('Il passivo fiscale/previdenziale deve essere modellato per scadenza e trattamento, non come aggregato.')
    if d.get('debiti_fornitori'): points.append('Il debito fornitori richiede ageing e segmentazione per impatto sulla continuità.')
    if d.get('crediti_totali') and d.get('ricavi_correnti') and d['crediti_totali']>d['ricavi_correnti']*3:
        points.append('Crediti molto elevati rispetto ai ricavi caratteristici: verificare concentrazione, parti correlate, recuperabilità e calendario incassi.')
    if not points: points.append('Nessuna conclusione robusta senza validazione delle rettifiche e del cash flow prospettico.')
    return points
