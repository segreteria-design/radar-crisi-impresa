def project_5y(d,nm,assumptions):
    rev0=nm.get('ricavi_operativi_normalizzati') or d.get('valore_produzione') or d.get('ricavi_correnti') or 0
    tax_debt=(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    suppliers=d.get('debiti_fornitori') or 0
    fin=d.get('debito_finanziario') or 0
    haircut=float(assumptions.get('falcidia_fiscale',0.0)); tax_post=tax_debt*(1-haircut)
    years=max(1,int(assumptions.get('anni_fisco',10))); quota_tax=tax_post/years
    fin_service=float(assumptions.get('servizio_finanziario_annuo',0.0))
    supplier_service=float(assumptions.get('rientro_fornitori_annuo',0.0))
    tax_rate=float(assumptions.get('tax_rate',0.0))
    out=[]; rev=rev0
    prev_ccn=assumptions.get('ccn_iniziale')
    for y in range(1,6):
        g=assumptions.get('growth',[.03]*5)[y-1]; margin=assumptions.get('margin',[.10]*5)[y-1]
        dso=assumptions.get('dso',[90]*5)[y-1]; dio=assumptions.get('dio',[30]*5)[y-1]; dpo=assumptions.get('dpo',[90]*5)[y-1]
        capex=assumptions.get('capex',[0]*5)[y-1]; cash_cost_ratio=assumptions.get('cash_cost_ratio',[.25]*5)[y-1]
        rev*=1+g; ebitda=rev*margin
        ar=rev*dso/365; inventory=rev*cash_cost_ratio*dio/365; ap=rev*cash_cost_ratio*dpo/365
        ccn=ar+inventory-ap
        dccn=0.0 if prev_ccn is None else ccn-prev_ccn
        prev_ccn=ccn
        cash_taxes=max(0,ebitda*tax_rate)
        cfads=ebitda-dccn-capex-cash_taxes
        debt_service=quota_tax+fin_service+supplier_service
        dscr=cfads/debt_service if debt_service else None
        out.append({'anno':y,'ricavi_operativi':rev,'ebitda':ebitda,'ebitda_margin':margin,'crediti_operativi':ar,'rimanenze_proxy':inventory,'fornitori_operativi':ap,'ccn':ccn,'delta_ccn':dccn,'capex':capex,'cash_taxes':cash_taxes,'cfads':cfads,'servizio_debito':debt_service,'dscr':dscr,'surplus_cassa':cfads-debt_service})
    return out


def scenario_grid(d,nm,base_assumptions):
    scenarios={
        'Downside':{'growth_shift':-.03,'margin_shift':-.03},
        'Base':{'growth_shift':0,'margin_shift':0},
        'Upside':{'growth_shift':.03,'margin_shift':.03},
    }
    rows=[]
    for name,sh in scenarios.items():
        a=dict(base_assumptions)
        a['growth']=[max(-.30,x+sh['growth_shift']) for x in base_assumptions['growth']]
        a['margin']=[max(-.30,x+sh['margin_shift']) for x in base_assumptions['margin']]
        p=project_5y(d,nm,a)
        rows.append({'scenario':name,'ricavi_y5':p[-1]['ricavi_operativi'],'ebitda_y5':p[-1]['ebitda'],'dscr_min':min([x['dscr'] for x in p if x['dscr'] is not None],default=None),'surplus_cumulato':sum(x['surplus_cassa'] for x in p)})
    return rows
