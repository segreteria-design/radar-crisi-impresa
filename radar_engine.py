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
    doc = fitz.open(stream=data, filetype='pdf')
    pages, used_ocr = [], False
    for i, p in enumerate(doc):
        if i >= max_pages:
            break
        text = p.get_text('text') or ''
        if ocr and len(re.sub(r'\s+', '', text)) < 120:
            pix = p.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            try:
                text = pytesseract.image_to_string(img, lang='ita')
            except Exception:
                text = pytesseract.image_to_string(img)
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


def structured_value(text, labels, *, lo=None, hi=None, evidence=None, key=None):
    lines=_lines(text); candidates=[]
    for label in labels:
        for i,line in enumerate(lines):
            if not _label_match(line,label):
                continue
            low=line.lower(); pos=low.find(label.lower()); tail=line[pos+len(label):] if pos>=0 else line
            euro_m=re.search(r'(?:euro|€)\s*('+NUM_RE+r')',tail,re.I)
            if euro_m:
                candidates.append((it_num(euro_m.group(1)),.98,line)); continue
            same=_nums(tail)
            if same and len(line)<130:
                candidates.append((same[0],.96,line)); continue
            # table extraction frequently places current-year amount on next line
            for j in range(i+1,min(i+3,len(lines))):
                n=_nums(lines[j])
                if n and len(lines[j])<60:
                    candidates.append((n[0],.93,f'{line} -> {lines[j]}')); break
            context=' '.join(lines[i:min(i+4,len(lines))])
            m=re.search(r'(?:pari\s+a|ammonta(?:no)?\s+a|per\s+euro|euro|€)\s*('+NUM_RE+r')',context,re.I)
            if m:
                candidates.append((it_num(m.group(1)),.86,context[:260]))
    cleaned=[]
    for v,conf,ev in candidates:
        if v is None: continue
        if lo is not None and abs(v)<lo: continue
        if hi is not None and abs(v)>hi: continue
        cleaned.append((v,conf,ev))
    if not cleaned: return None
    cleaned.sort(key=lambda x:x[1],reverse=True)
    v,conf,ev=cleaned[0]
    if evidence is not None and key:
        evidence[key]={'confidence':conf,'evidence':ev}
    return v


def extract_company_name(text,evidence=None):
    lines=_lines(text)
    for i,line in enumerate(lines):
        if _label_match(line,'Denominazione') or _label_match(line,'Ragione sociale'):
            tail=re.split(r'[:\-]',line,maxsplit=1)
            cand=tail[-1].strip() if len(tail)>1 else ''
            if cand and re.search(r'\b(SRL|S\.R\.L\.|SPA|S\.P\.A\.)\b',cand,re.I):
                if evidence is not None: evidence['ragione_sociale']={'confidence':.99,'evidence':line}
                return cand
            if i+1<len(lines):
                cand=lines[i+1]
                if re.search(r'\b(SRL|S\.R\.L\.|SPA|S\.P\.A\.)\b',cand,re.I):
                    if evidence is not None: evidence['ragione_sociale']={'confidence':.97,'evidence':f'{line} -> {cand}'}
                    return cand
    return None


def extract_fields_with_meta(text):
    ev={}; f={}
    f['ragione_sociale']=extract_company_name(text,ev)
    mapping={
        'ricavi_correnti':['Ricavi delle vendite e delle prestazioni','ricavi delle vendite e delle prestazioni'],
        'valore_produzione':['Totale valore della produzione','Valore della produzione'],
        'altri_ricavi_proventi':['Totale altri ricavi e proventi','Altri ricavi e proventi'],
        'contributi_esercizio':['contributi in conto esercizio'],
        'ebit':['Differenza tra valore e costi della produzione','Risultato operativo','EBIT - Risultato operativo'],
        'ammortamenti_immateriali':['ammortamento delle immobilizzazioni immateriali'],
        'ammortamenti_materiali':['ammortamento delle immobilizzazioni materiali'],
        'svalutazioni_crediti':['svalutazioni dei crediti compresi nell attivo circolante','svalutazioni dei crediti'],
        'risultato_netto':["Utile (perdita) dell'esercizio",'Utile perdita dell esercizio'],
        'liquidita':['Totale disponibilita liquide','Totale disponibilità liquide','Disponibilita liquide'],
        'debiti_banche':['Debiti verso banche'],
        'debiti_altri_fin':['Debiti verso altri finanziatori'],
        'debiti_tributari':['Totale debiti tributari','Debiti tributari'],
        'debiti_previdenziali':['Totale debiti verso istituti di previdenza','Debiti verso istituti di previdenza e di sicurezza sociale','Debiti previdenziali'],
        'debiti_fornitori':['Totale debiti verso fornitori','Debiti verso fornitori'],
        'totale_debiti':['Totale debiti'],
        'patrimonio_netto':['Totale patrimonio netto','Patrimonio netto'],
        'attivo_circolante':['Totale attivo circolante','Attivo circolante'],
        'crediti_totali':['Totale crediti','Totale crediti iscritti nell attivo circolante'],
        'rimanenze':['Totale rimanenze'],
        'oneri_finanziari':['Totale interessi e altri oneri finanziari','Interessi e altri oneri finanziari'],
        'cash_flow_operativo':['Flusso finanziario dell attività operativa','Flusso finanziario dell attivita operativa'],
    }
    for k,labels in mapping.items():
        f[k]=structured_value(text,labels,lo=0 if k not in ('ebit','risultato_netto','cash_flow_operativo','patrimonio_netto') else None,hi=1e13,evidence=ev,key=k)
    f['debito_finanziario']=None
    if f.get('debiti_banche') is not None or f.get('debiti_altri_fin') is not None:
        f['debito_finanziario']=(f.get('debiti_banche') or 0)+(f.get('debiti_altri_fin') or 0)
        ev['debito_finanziario']={'confidence':.97,'evidence':'Somma debiti verso banche + altri finanziatori'}
    # EBITDA policy: EBIT + D&A only. Credit impairments are not added back by default.
    if f.get('ebit') is not None and (f.get('ammortamenti_immateriali') is not None or f.get('ammortamenti_materiali') is not None):
        f['ebitda'] = f['ebit'] + (f.get('ammortamenti_immateriali') or 0) + (f.get('ammortamenti_materiali') or 0)
        ev['ebitda']={'confidence':.88,'evidence':'Ricostruito come EBIT + ammortamenti immateriali + ammortamenti materiali (svalutazioni crediti escluse)'}
    else:
        f['ebitda']=structured_value(text,['EBITDA - Margine operativo lordo','EBITDA','Margine operativo lordo'],hi=1e13,evidence=ev,key='ebitda')
    # Working capital proxy when no explicit current liabilities are available.
    f['passivita_correnti']=structured_value(text,["Debiti esigibili entro l'esercizio successivo",'esigibili entro esercizio successivo'],lo=0,hi=1e13,evidence=ev,key='passivita_correnti')
    quality=validate_extraction(f,ev)
    return f,{'evidence':ev,**quality}


def validate_extraction(f,evidence=None):
    core=['ricavi_correnti','ebitda','debiti_tributari','debiti_fornitori','patrimonio_netto']
    useful=core+['valore_produzione','debito_finanziario','debiti_previdenziali','attivo_circolante','oneri_finanziari','cash_flow_operativo']
    found=sum(f.get(k) is not None for k in useful)
    missing_core=[k for k in core if f.get(k) is None]
    warnings=[]
    if missing_core: warnings.append('Mancano dati essenziali: '+', '.join(missing_core))
    if f.get('ebitda') is not None and f.get('valore_produzione') and abs(f['ebitda'])>abs(f['valore_produzione'])*2:
        warnings.append('EBITDA anomalo rispetto al valore della produzione: verifica estrazione.')
    return {'completeness':found/len(useful),'missing_core':missing_core,'warnings':warnings,'reliable':len(missing_core)<=1 and found>=6}


def extract_fields(text):
    f,_=extract_fields_with_meta(text); return f
