import re, io
import fitz
from PIL import Image
import pytesseract

NUM_RE = r"\(?-?\d{1,3}(?:[\.,]\d{3})+(?:,\d+)?\)?|\(?-?\d+(?:,\d+)?\)?"


def it_num(s):
    if s is None:
        return None
    s = str(s).strip().replace('€', '').replace('Euro', '').replace('euro', '').replace(' ', '')
    if not s:
        return None
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    if re.fullmatch(r'-?\d{1,3}(?:[\.,]\d{3})+', s):
        s = s.replace('.', '').replace(',', '')
    elif ',' in s and '.' not in s:
        parts = s.split(',')
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]):
            s = ''.join(parts)
        else:
            s = s.replace(',', '.')
    elif ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        p = s.rsplit('.', 1)
        if len(p) == 2 and len(p[1]) == 3:
            s = ''.join(p)
    try:
        v = float(s)
        return -v if neg and v > 0 else v
    except Exception:
        return None


def extract_pdf_text(data: bytes, ocr=True, max_pages=60):
    """Extract page-aware text. Scanned pages use psm 4 because statutory accounts are table-heavy."""
    doc = fitz.open(stream=data, filetype='pdf')
    pages, used_ocr = [], False
    for i, p in enumerate(doc):
        if i >= max_pages:
            break
        text = p.get_text('text') or ''
        if ocr and len(re.sub(r'\s+', '', text)) < 120:
            pix = p.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            try:
                text = pytesseract.image_to_string(img, lang='ita', config='--psm 4')
            except Exception:
                text = pytesseract.image_to_string(img, config='--psm 4')
            used_ocr = True
        pages.append(f"\n--- PAGINA {i+1} ---\n{text}")
    return '\n'.join(pages), used_ocr


def _lines(text):
    return [re.sub(r'\s+', ' ', x).strip() for x in text.splitlines() if x.strip()]


def _nums(s):
    vals=[]
    for raw in re.findall(NUM_RE, s or ''):
        v=it_num(raw)
        if v is not None:
            vals.append(v)
    return vals


def _norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def _label_match(line, label):
    return _norm(label) in _norm(line)


def _pages(text):
    out={}
    matches=list(re.finditer(r'--- PAGINA\s+(\d+)\s+---', text or '', flags=re.I))
    if not matches:
        return {0:text or ''}
    for n,m in enumerate(matches):
        start=m.end(); end=matches[n+1].start() if n+1<len(matches) else len(text)
        out[int(m.group(1))]=text[start:end]
    return out


def _row_candidate(line, label, current_year_index=0):
    """Return first numeric column after an accounting row label."""
    if not _label_match(line,label):
        return None
    nl=_norm(line); lb=_norm(label)
    # Generic total labels must not capture sub-totals such as 'Totale debiti verso fornitori'.
    if lb == 'totale debiti' and nl.startswith('totale debiti '):
        rest=nl[len('totale debiti '):]
        if rest and not rest[0].isdigit() and rest[0] not in '(-':
            return None
    if lb == 'totale crediti' and nl.startswith('totale crediti '):
        rest=nl[len('totale crediti '):]
        if rest and not rest[0].isdigit() and rest[0] not in '(-':
            return None
    # Reject narrative/legal lines; table rows are usually short and numeric-rich.
    nums=_nums(line)
    if not nums or len(line)>180:
        return None
    # Drop numbering before the label, e.g. "12) debiti tributari".
    pos=_norm(line).find(_norm(label))
    if pos>=0:
        raw_tail=line.lower().find(label.lower())
        tail=line[raw_tail+len(label):] if raw_tail>=0 else line
        n2=_nums(tail)
        if n2: nums=n2
    return nums[current_year_index] if len(nums)>current_year_index else None


def table_value(text, labels, page_range=None, evidence=None, key=None, lo=None, hi=None):
    ps=_pages(text); candidates=[]
    items=ps.items() if page_range is None else [(p,ps.get(p,'')) for p in page_range if p in ps]
    for p,chunk in items:
        for line in _lines(chunk):
            for label in labels:
                v=_row_candidate(line,label)
                if v is None: continue
                if lo is not None and abs(v)<lo: continue
                if hi is not None and abs(v)>hi: continue
                # Exact total labels have highest weight.
                conf=.995 if _norm(line).startswith(_norm(label)) else .97
                candidates.append((v,conf,p,line))
    if not candidates: return None
    candidates.sort(key=lambda x:x[1],reverse=True)
    v,conf,p,line=candidates[0]
    if evidence is not None and key:
        evidence[key]={'confidence':conf,'evidence':f'Pag. {p}: {line}','page':p,'method':'table'}
    return v


def narrative_amount(text, patterns, *, evidence=None, key=None, page_range=None, lo=None, hi=None):
    ps=_pages(text); candidates=[]
    items=ps.items() if page_range is None else [(p,ps.get(p,'')) for p in page_range if p in ps]
    for p,chunk in items:
        flat=' '.join(_lines(chunk))
        for pat in patterns:
            m=re.search(pat,flat,re.I)
            if not m: continue
            v=it_num(m.group(1))
            if v is None: continue
            if lo is not None and abs(v)<lo: continue
            if hi is not None and abs(v)>hi: continue
            ev=flat[max(0,m.start()-100):min(len(flat),m.end()+140)]
            candidates.append((v,.99,p,ev))
    if not candidates:return None
    v,conf,p,ev=candidates[0]
    if evidence is not None and key:
        evidence[key]={'confidence':conf,'evidence':f'Pag. {p}: {ev}','page':p,'method':'narrative'}
    return v


def structured_value(text, labels, *, lo=None, hi=None, evidence=None, key=None, page_range=None):
    # First try table rows, then restrained narrative extraction.
    v=table_value(text,labels,page_range=page_range,evidence=evidence,key=key,lo=lo,hi=hi)
    if v is not None:return v
    ps=_pages(text); candidates=[]
    items=ps.items() if page_range is None else [(p,ps.get(p,'')) for p in page_range if p in ps]
    for p,chunk in items:
        lines=_lines(chunk)
        for label in labels:
            for i,line in enumerate(lines):
                if not _label_match(line,label):continue
                context=' '.join(lines[i:min(i+3,len(lines))])
                m=re.search(r'(?:ammonta(?:no)?\s+a|per\s+(?:un\s+)?importo(?:\s+complessivo)?\s+di\s+euro|per\s+euro|euro|€)\s*('+NUM_RE+r')',context,re.I)
                if not m:continue
                val=it_num(m.group(1))
                if val is None:continue
                if lo is not None and abs(val)<lo:continue
                if hi is not None and abs(val)>hi:continue
                candidates.append((val,.90,p,context[:300]))
    if not candidates:return None
    v,conf,p,ev=candidates[0]
    if evidence is not None and key:
        evidence[key]={'confidence':conf,'evidence':f'Pag. {p}: {ev}','page':p,'method':'context'}
    return v


def extract_company_name(text,evidence=None):
    lines=_lines(text)
    for i,line in enumerate(lines):
        if _label_match(line,'Denominazione') or _label_match(line,'Ragione sociale'):
            tail=re.split(r'[:\-]',line,maxsplit=1)
            cand=tail[-1].strip() if len(tail)>1 else ''
            if cand and re.search(r'\b(SRL|S\.R\.L\.|SPA|S\.P\.A\.)\b',cand,re.I):
                if evidence is not None:evidence['ragione_sociale']={'confidence':.99,'evidence':line,'method':'label'}
                return cand
            if i+1<len(lines):
                cand=lines[i+1]
                if re.search(r'\b(SRL|S\.R\.L\.|SPA|S\.P\.A\.)\b',cand,re.I):
                    if evidence is not None:evidence['ragione_sociale']={'confidence':.97,'evidence':f'{line} -> {cand}','method':'label'}
                    return cand
    # OCR fallback: repeated legal entity line on scanned accounts.
    for line in lines:
        if re.search(r'\b(?:FOOTBALL|AUTOMOTIVE|HOLDING|INDUSTRIE|SERVIZI|SOCIETA)\b',line,re.I) and re.search(r'\b(SRL|S\.R\.L\.|SPA|S\.P\.A\.)\b',line,re.I):
            if evidence is not None:evidence['ragione_sociale']={'confidence':.78,'evidence':line,'method':'ocr_fallback'}
            return line.strip()
    return None


def _pick(text, key, labels, ev, pages=None, lo=0, hi=1e13):
    return structured_value(text,labels,lo=lo,hi=hi,evidence=ev,key=key,page_range=pages)


def extract_fields_with_meta(text):
    ev={}; f={}
    f['ragione_sociale']=extract_company_name(text,ev)
    # Statutory statements normally sit in the first 6-7 pages. Restricting scope prevents note-text false matches.
    f['ricavi_correnti']=_pick(text,'ricavi_correnti',['ricavi delle vendite e delle prestazioni'],ev,range(1,8))
    f['valore_produzione']=_pick(text,'valore_produzione',['Totale valore della produzione'],ev,range(1,8))
    f['altri_ricavi_proventi']=_pick(text,'altri_ricavi_proventi',['Totale altri ricavi e proventi'],ev,range(1,8))
    f['contributi_esercizio']=_pick(text,'contributi_esercizio',['contributi in conto esercizio'],ev,range(1,8))
    f['ebit']=structured_value(text,['Differenza tra valore e costi della produzione'],lo=None,hi=1e13,evidence=ev,key='ebit',page_range=range(1,8))
    f['ammortamenti_immateriali']=_pick(text,'ammortamenti_immateriali',['ammortamento delle immobilizzazioni immateriali'],ev,range(1,8))
    f['ammortamenti_materiali']=_pick(text,'ammortamenti_materiali',['ammortamento delle immobilizzazioni materiali'],ev,range(1,8))
    f['svalutazioni_crediti']=_pick(text,'svalutazioni_crediti',['svalutazioni dei crediti compresi nell attivo circolante','svalutazioni dei crediti'],ev,range(1,8))
    f['risultato_netto']=structured_value(text,["Utile (perdita) dell'esercizio",'Utile perdita dell esercizio'],lo=None,hi=1e13,evidence=ev,key='risultato_netto',page_range=range(1,8))
    f['liquidita']=_pick(text,'liquidita',['Totale disponibilità liquide','Totale disponibilita liquide'],ev,range(1,8))
    f['rimanenze']=_pick(text,'rimanenze',['Totale rimanenze'],ev,range(1,8))
    f['debiti_banche']=_pick(text,'debiti_banche',['Totale debiti verso banche','Debiti verso banche'],ev,range(1,8))
    f['debiti_altri_fin']=_pick(text,'debiti_altri_fin',['Totale debiti verso altri finanziatori','Debiti verso altri finanziatori'],ev,range(1,8))
    f['debiti_tributari']=_pick(text,'debiti_tributari',['Totale debiti tributari'],ev,range(1,8))
    f['debiti_previdenziali']=_pick(text,'debiti_previdenziali',['Totale debiti verso istituti di previdenza e di sicurezza sociale'],ev,range(1,8))
    f['debiti_fornitori']=_pick(text,'debiti_fornitori',['Totale debiti verso fornitori'],ev,range(1,8))
    f['totale_debiti']=_pick(text,'totale_debiti',['Totale debiti'],ev,range(1,8))
    f['patrimonio_netto']=_pick(text,'patrimonio_netto',['Totale patrimonio netto'],ev,range(1,8),lo=None)
    f['attivo_circolante']=_pick(text,'attivo_circolante',['Totale attivo circolante'],ev,range(1,8))
    f['crediti_totali']=_pick(text,'crediti_totali',['Totale crediti iscritti nell attivo circolante','Totale crediti'],ev,range(1,8))
    f['oneri_finanziari']=_pick(text,'oneri_finanziari',['Totale interessi e altri oneri finanziari'],ev,range(1,8))
    f['cash_flow_operativo']=structured_value(text,['Flusso finanziario dell attività operativa','Flusso finanziario dell attivita operativa'],lo=None,hi=1e13,evidence=ev,key='cash_flow_operativo',page_range=range(1,9))

    # Narrative cross-check / rescue. These formulations are common in Italian XBRL notes and much safer than generic keyword matching.
    rescues={
        'crediti_totali': [r'importo totale dei crediti[^.]{0,180}?importo complessivo di euro\s*('+NUM_RE+r')'],
        'totale_debiti': [r'importo totale dei debiti[^.]{0,180}?importo complessivo di euro\s*('+NUM_RE+r')'],
        'patrimonio_netto':[r'il patrimonio netto ammonta a euro\s*('+NUM_RE+r')'],
        'liquidita':[r'disponibilit[aà] liquide[^.]{0,240}?per euro\s*('+NUM_RE+r')'],
    }
    for key,pats in rescues.items():
        val=narrative_amount(text,pats,evidence=ev,key=key+'_crosscheck',lo=None if key=='patrimonio_netto' else 0,hi=1e13)
        # Prefer high-confidence narrative totals when statement OCR produced implausible tiny values.
        if val is not None and (f.get(key) is None or abs(f.get(key) or 0)<max(1000,abs(val)*0.02)):
            f[key]=val; ev[key]=ev[key+'_crosscheck']

    # Note-detail rescue for debt components where OCR of the balance sheet can be weak.
    for key,labels in {
        'debiti_tributari':['Debiti tributari'],
        'debiti_previdenziali':['Debiti verso istituti di previdenza e di sicurezza sociale'],
        'debiti_fornitori':['Debiti verso fornitori'],
    }.items():
        v=table_value(text,labels,page_range=range(28,33),evidence=ev,key=key+'_note',lo=1000,hi=1e13)
        if v is not None and (f.get(key) is None or abs(f.get(key) or 0)<1000):
            f[key]=v; ev[key]=ev[key+'_note']

    f['debito_finanziario']=None
    if f.get('debiti_banche') is not None or f.get('debiti_altri_fin') is not None:
        f['debito_finanziario']=(f.get('debiti_banche') or 0)+(f.get('debiti_altri_fin') or 0)
        ev['debito_finanziario']={'confidence':.97,'evidence':'Somma debiti verso banche + altri finanziatori','method':'derived'}

    # EBITDA policy: EBIT + D&A only. Credit impairments are not added back by default.
    if f.get('ebit') is not None and (f.get('ammortamenti_immateriali') is not None or f.get('ammortamenti_materiali') is not None):
        f['ebitda'] = f['ebit'] + (f.get('ammortamenti_immateriali') or 0) + (f.get('ammortamenti_materiali') or 0)
        ev['ebitda']={'confidence':.96,'evidence':'Ricostruito come EBIT + ammortamenti immateriali + ammortamenti materiali; svalutazioni crediti escluse','method':'derived'}
    else:
        f['ebitda']=structured_value(text,['EBITDA - Margine operativo lordo','EBITDA','Margine operativo lordo'],hi=1e13,evidence=ev,key='ebitda')

    f['passivita_correnti']=structured_value(text,["Debiti esigibili entro l'esercizio successivo",'esigibili entro esercizio successivo'],lo=0,hi=1e13,evidence=ev,key='passivita_correnti',page_range=range(1,8))
    quality=validate_extraction(f,ev)
    return f,{'evidence':ev,**quality}


def validate_extraction(f,evidence=None):
    core=['ricavi_correnti','ebitda','debiti_tributari','debiti_fornitori','patrimonio_netto']
    useful=core+['valore_produzione','totale_debiti','crediti_totali','debito_finanziario','debiti_previdenziali','attivo_circolante','oneri_finanziari','cash_flow_operativo']
    found=sum(f.get(k) is not None for k in useful)
    missing_core=[k for k in core if f.get(k) is None]
    warnings=[]; hard=[]
    if missing_core: warnings.append('Mancano dati essenziali: '+', '.join(missing_core))
    if f.get('ebitda') is not None and f.get('valore_produzione') and abs(f['ebitda'])>abs(f['valore_produzione'])*1.5:
        hard.append('EBITDA anomalo rispetto al valore della produzione.')
    # Accounting consistency tests: totals cannot be smaller than their major components.
    debt_components=sum(max(0,f.get(k) or 0) for k in ['debiti_tributari','debiti_previdenziali','debiti_fornitori','debito_finanziario'])
    if f.get('totale_debiti') is not None and debt_components and f['totale_debiti']+1 < debt_components*0.98:
        hard.append('Totale debiti inferiore alla somma delle principali componenti: estrazione incoerente.')
    if f.get('crediti_totali') is not None and f.get('ricavi_correnti') and f['crediti_totali']<0:
        hard.append('Crediti totali negativi: estrazione incoerente.')
    for k in ['debiti_tributari','debiti_previdenziali','debiti_fornitori','totale_debiti','crediti_totali']:
        if f.get(k) is not None and 0<abs(f[k])<100:
            hard.append(f'{k}: valore sospetto ({f[k]:.0f}); probabile numero di riga/nota catturato come importo.')
    completeness=found/len(useful)
    reliable=(len(missing_core)==0 and found>=9 and not hard)
    warnings.extend(hard)
    return {'completeness':completeness,'missing_core':missing_core,'warnings':warnings,'hard_errors':hard,'reliable':reliable}


def extract_fields(text):
    f,_=extract_fields_with_meta(text); return f
