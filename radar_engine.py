import re, io, json, math
from pathlib import Path
import fitz
from PIL import Image
import pytesseract

NUM_RE = r"\(?-?\d{1,3}(?:[\.,]\d{3})+(?:,\d+)?\)?|\(?-?\d+\)?"

def it_num(s):
    if s is None: return None
    s=str(s).strip().replace('€','').replace(' ','')
    neg=s.startswith('(') and s.endswith(')')
    s=s.strip('()')
    # Italian statements use . as thousands separator; OCR may turn it into comma.
    if re.fullmatch(r'\d{1,3}(?:[\.,]\d{3})+', s):
        s=s.replace('.','').replace(',','')
    elif ',' in s and '.' not in s:
        parts=s.split(',')
        s=''.join(parts) if all(len(x)==3 for x in parts[1:]) else s.replace(',','.')
    else:
        s=s.replace('.','')
    try:
        v=float(s)
        return -v if neg else v
    except: return None

def extract_pdf_text(data: bytes, ocr=True, max_pages=30):
    doc=fitz.open(stream=data, filetype='pdf')
    pages=[]; used_ocr=False
    for i,p in enumerate(doc):
        if i>=max_pages: break
        text=p.get_text('text') or ''
        if ocr and len(re.sub(r'\s+','',text)) < 120:
            pix=p.get_pixmap(matrix=fitz.Matrix(2.1,2.1), alpha=False)
            img=Image.open(io.BytesIO(pix.tobytes('png')))
            text=pytesseract.image_to_string(img, lang='ita')
            used_ocr=True
        pages.append(text)
    return '\n'.join(pages), used_ocr

def line_value(text, labels, prefer='first'):
    lines=[re.sub(r'\s+',' ',x).strip() for x in text.splitlines() if x.strip()]
    for label in labels:
        ll=label.lower()
        for idx,line in enumerate(lines):
            if ll in line.lower():
                # Same line first
                tail=line.lower().split(ll,1)[-1]
                nums=re.findall(NUM_RE, tail)
                if nums:
                    vals=[it_num(n) for n in nums if it_num(n) is not None]
                    if vals: return vals[0] if prefer=='first' else vals[-1]
                # then nearby lines for tables where value is separated
                for j in range(idx+1, min(idx+3,len(lines))):
                    nums=re.findall(NUM_RE, lines[j])
                    vals=[it_num(n) for n in nums if it_num(n) is not None]
                    if vals: return vals[0]
    return None

def regex_value(text, patterns):
    for pat in patterns:
        m=re.search(pat,text,re.I|re.S)
        if m:
            v=it_num(m.group(1))
            if v is not None: return v
    return None

def extract_fields(text):
    f={}
    m=re.search(r'\b([A-Z][A-Z0-9 &\.\-]{2,60}(?:SRL|S\.R\.L\.|SPA|S\.P\.A\.))\b', text, re.I)
    f['ragione_sociale']=' '.join(m.group(1).split()) if m else None

    def val(patterns, choose='first', lo=None, hi=None):
        vals=[]
        for pat in patterns:
            for m in re.finditer(pat,text,re.I|re.S):
                v=it_num(m.group(1))
                if v is None: continue
                if lo is not None and abs(v)<lo: continue
                if hi is not None and abs(v)>hi: continue
                vals.append(v)
        if not vals: return None
        if choose=='maxabs': return max(vals,key=lambda x:abs(x))
        if choose=='max': return max(vals)
        if choose=='minabs': return min(vals,key=lambda x:abs(x))
        return vals[0]


    def line_nums(keyword):
        out=[]
        for line in text.splitlines():
            if keyword.lower() in line.lower():
                out.extend([it_num(x) for x in re.findall(NUM_RE,line)])
        return [x for x in out if x is not None]

    # Revenue: prefer a positive number immediately before a later 'Ricavi vendite e prestazioni'
    revs=[]
    for m in re.finditer(r'Ricavi\s+(?:delle\s+)?vendite(?:\s+e\s+(?:delle\s+)?prestazioni)?',text,re.I):
        pre=text[max(0,m.start()-220):m.start()]
        nums=[it_num(x) for x in re.findall(NUM_RE,pre)]
        nums=[x for x in nums if x and 10000 <= x <= 1e10]
        if nums: revs.append(max(nums))
        post=text[m.end():m.end()+120]
        nums=[it_num(x) for x in re.findall(NUM_RE,post)]
        nums=[x for x in nums if x and 10000 <= x <= 1e10]
        if nums: revs.append(nums[0])
    # Prefer repeated/plausible lower number over total production; largest candidate can be previous-year revenue.
    f['ricavi_correnti']=min(revs) if revs else None
    # if OCR page has clear current value near note table, prefer smallest candidate >100k (often current/previous; this is conservative and user-verifiable)
    if revs:
        cands=[x for x in revs if x>100000]
        if cands: f['ricavi_correnti']=min(cands)

    f['risultato_netto']=val([rf"Utile\s*\(perdita\)\s+dell.?esercizio[^\n]*?({NUM_RE})"], choose='first', hi=1e9)
    f['liquidita']=val([rf"Totale\s+disponibilit[aà]\s+liquide[^\n]*?({NUM_RE})",rf"Disponibilit[aà]\s+liquide[^\n]*?({NUM_RE})"], choose='maxabs', lo=100, hi=1e10)
    f['debiti_banche']=val([rf"Debiti\s+verso\s+banche[^\n]*?({NUM_RE})"], choose='first', hi=1e10)
    f['debiti_altri_fin']=val([rf"Debiti\s+verso\s+altri\s+finanziatori[^\n]*?({NUM_RE})"], choose='first', hi=1e10)
    f['debito_finanziario']=((f['debiti_banche'] or 0)+(f['debiti_altri_fin'] or 0)) if (f['debiti_banche'] is not None or f['debiti_altri_fin'] is not None) else None
    _tx=line_nums('Debiti tributari'); f['debiti_tributari']=max(_tx,key=lambda x:abs(x)) if _tx else val([rf"Debiti\s+tributari[^\n]*?({NUM_RE})"], choose='maxabs', lo=100,hi=1e10)
    _pr=line_nums('previdenza'); _pr=[x for x in _pr if 100 <= abs(x) <= 1e10]; f['debiti_previdenziali']=max(_pr,key=lambda x:abs(x)) if _pr else None
    f['debiti_fornitori']=val([rf"Debiti\s+verso\s+fornitori[^\n]*?({NUM_RE})"], choose='maxabs', lo=100,hi=1e10)
    f['patrimonio_netto']=val([rf"Totale\s+patrimonio\s+netto[^\n]*?({NUM_RE})"], choose='first', hi=1e10)
    f['attivo_circolante']=val([rf"Totale\s+attivo\s+circolante[^\n]*?({NUM_RE})"], choose='first', lo=100,hi=1e10)
    # Restrict current liabilities to balance-sheet debt section
    mdeb=re.search(r"D\)\s*Debiti(.*?)(?:Totale\s+debiti[^\n]*\n?)",text,re.I|re.S)
    debtsec=mdeb.group(1) if mdeb else text
    f['passivita_correnti']=regex_value(debtsec,[rf"esigibili\s+entro\s+l.?esercizio\s+successivo[^\d\(\-]*({NUM_RE})"])
    f['totale_debiti']=val([rf"Totale\s+debiti[^\n]*?({NUM_RE})"],choose='maxabs',lo=100,hi=1e11)
    f['oneri_finanziari']=val([rf"Totale\s+interessi\s+e\s+altri\s+oneri\s+finanziari[^\n]*?({NUM_RE})",rf"interessi\s+e\s+altri\s+oneri\s+finanziari[^\n]*?({NUM_RE})"],choose='maxabs',lo=1,hi=1e9)
    ebit=val([rf"Differenza\s+tra\s+valore\s+e\s+costi\s+della\s+produzione[^\n]*?({NUM_RE})"],choose='first',hi=1e9)
    amm=val([rf"Totale\s+ammortamenti\s+e\s+svalutazioni[^\n]*?({NUM_RE})"],choose='first',hi=1e9)
    f['ebit']=ebit; f['ammortamenti']=amm; f['ebitda']=(ebit+amm) if ebit is not None and amm is not None else None
    return f

def clamp(v,a,b): return max(a,min(b,v))

def score(d, qual=None):
    q=qual or {}
    rev=d.get('ricavi_correnti') or 0
    ebitda=d.get('ebitda') or 0
    tax=(d.get('debiti_tributari') or 0)+(d.get('debiti_previdenziali') or 0)
    fin=d.get('debito_finanziario') or 0
    suppliers=d.get('debiti_fornitori') or 0
    ca=d.get('attivo_circolante') or 0
    cl=d.get('passivita_correnti') or 0
    equity=d.get('patrimonio_netto')
    # Financial distress /15
    fs=0
    if ebitda>0:
        lev=fin/ebitda
        fs += 5 if lev>=6 else 4 if lev>=4 else 3 if lev>=3 else 1 if lev>=1.5 else 0
    elif fin>0: fs+=5
    if cl>0 and ca/cl<1: fs+=4
    if equity is not None and equity<0: fs+=4
    elif equity is not None and equity<0.1*rev: fs+=2
    if d.get('oneri_finanziari') and ebitda>0 and ebitda/d['oneri_finanziari']<1.5: fs+=2
    fs=clamp(fs,0,15)
    # Fiscal /15
    ts=0
    if rev>0:
        tr=tax/rev
        ts += 8 if tr>=0.40 else 6 if tr>=0.25 else 4 if tr>=0.10 else 2 if tr>=0.05 else 0
    if ebitda>0:
        te=tax/ebitda
        ts += 5 if te>=10 else 4 if te>=6 else 3 if te>=3 else 1 if te>=1 else 0
    elif tax>0: ts+=5
    if tax>0: ts+=2
    ts=clamp(ts,0,15)
    # Trade /10
    trs=0
    if rev>0:
        sr=suppliers/rev
        trs += 5 if sr>=0.25 else 4 if sr>=0.15 else 2 if sr>=0.08 else 0
    if cl>0 and ca/cl<1: trs+=3
    if suppliers>0: trs+=2
    trs=clamp(trs,0,10)
    comp=fs+ts+trs
    # Viability /20: neutral-conservative if little data
    vs=0
    if ebitda>0:
        margin=ebitda/rev if rev else 0
        vs += 8 if margin>=0.10 else 6 if margin>=0.05 else 4 if margin>0 else 0
    if d.get('risultato_netto') is not None: vs += 3 if d['risultato_netto']>=0 else 1
    vs += int(q.get('continuita',3))*2  # 2..10
    vs=clamp(vs,0,20)
    restruct = clamp(int(q.get('ristrutturabilita',3))*4,0,20)
    assets = clamp(int(q.get('asset_strategici',3))*2,0,10)
    feas = clamp(int(q.get('fattibilita_deal',3))*2,0,10)
    penalty=5 if q.get('red_flag',False) else 0
    total=clamp(comp+vs+restruct+assets+feas-penalty,0,100)
    cls='A' if total>=80 else 'B' if total>=70 else 'C' if total>=60 else 'D' if total>=40 else 'E'
    fit='FIT-A' if ts>=12 and vs>=8 and restruct>=12 and not q.get('red_flag',False) else 'FIT-B' if ts>=8 and restruct>=8 else 'NO-FIT'
    return {'finanziario':fs,'fiscale':ts,'commerciale':trs,'composito':comp,'continuita':vs,'ristrutturabilita':restruct,'asset':assets,'fattibilita':feas,'penalita':penalty,'totale':round(total,1),'classe':cls,'fit':fit}
