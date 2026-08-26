import re, io, math
import fitz
from PIL import Image
import pytesseract

NUM_RE = r"\(?-?\d{1,3}(?:[\.,]\d{3})+(?:,\d+)?\)?|\(?-?\d+(?:,\d+)?\)?"


def it_num(s):
    if s is None:
        return None
    s = str(s).strip().replace('€', '').replace('Euro', '').replace(' ', '')
    if not s:
        return None
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    # Italian accounting convention: dot/comma can be thousands separators.
    if re.fullmatch(r'-?\d{1,3}(?:[\.,]\d{3})+', s):
        s = s.replace('.', '').replace(',', '')
    elif ',' in s and '.' not in s:
        parts = s.split(',')
        if len(parts) > 1 and all(len(x) == 3 for x in parts[1:]):
            s = ''.join(parts)
        else:
            s = s.replace(',', '.')
    else:
        # if both separators exist, assume dot thousands and comma decimal
        if ',' in s and '.' in s:
            s = s.replace('.', '').replace(',', '.')
        elif '.' in s:
            # single dot with three trailing digits is usually thousands separator
            p = s.rsplit('.', 1)
            if len(p) == 2 and len(p[1]) == 3:
                s = ''.join(p)
    try:
        v = float(s)
        return -v if neg and v > 0 else v
    except Exception:
        return None


def extract_pdf_text(data: bytes, ocr=True, max_pages=40):
    doc = fitz.open(stream=data, filetype='pdf')
    pages = []
    used_ocr = False
    for i, p in enumerate(doc):
        if i >= max_pages:
            break
        text = p.get_text('text') or ''
        if ocr and len(re.sub(r'\s+', '', text)) < 120:
            pix = p.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes('png')))
            try:
                text = pytesseract.image_to_string(img, lang='ita')
            except Exception:
                text = pytesseract.image_to_string(img)
            used_ocr = True
        pages.append(text)
    return '\n'.join(pages), used_ocr


def _lines(text):
    return [re.sub(r'\s+', ' ', x).strip() for x in text.splitlines() if x.strip()]


def _nums(s):
    vals = []
    for raw in re.findall(NUM_RE, s or ''):
        v = it_num(raw)
        if v is not None:
            vals.append(v)
    return vals


def _label_match(line, label):
    line_n = re.sub(r'[^a-z0-9]+', ' ', line.lower()).strip()
    lab_n = re.sub(r'[^a-z0-9]+', ' ', label.lower()).strip()
    return lab_n in line_n


def structured_value(text, labels, *, lo=None, hi=None, prefer='current', evidence=None, key=None):
    """Find a label row and read its current-year value conservatively.

    Order of preference:
    1) numbers on the same line after the label;
    2) first numeric line immediately after the label (typical PDF table extraction);
    3) explicit prose 'pari a Euro ...' near the label.
    It never scans arbitrarily far into the next accounting row.
    """
    lines = _lines(text)
    candidates = []
    for label in labels:
        for i, line in enumerate(lines):
            if not _label_match(line, label):
                continue
            # Same line: remove text through the matched label and inspect tail.
            low = line.lower()
            pos = low.find(label.lower())
            tail = line[pos + len(label):] if pos >= 0 else line
            # In prose, prefer an amount explicitly introduced by Euro/€; this avoids
            # mistaking dates such as '31 dicembre 2024' for the accounting value.
            euro_m = re.search(r'(?:euro|€)\s*(' + NUM_RE + r')', tail, re.I)
            if euro_m:
                candidates.append((it_num(euro_m.group(1)), 0.98, f'{line}'))
                continue
            same = _nums(tail)
            if same and len(line) < 90:
                candidates.append((same[0], 0.98, f'{line}'))
                continue
            # Typical extracted table: label, current, previous on next lines.
            if i + 1 < len(lines):
                n1 = _nums(lines[i + 1])
                if n1 and len(lines[i + 1]) < 40:
                    candidates.append((n1[0], 0.96, f'{line} -> {lines[i+1]}'))
                    continue
            # Prose within very tight context.
            context = ' '.join(lines[i:min(i + 3, len(lines))])
            m = re.search(r'(?:pari\s+a|ammonta(?:no)?\s+a|ammontano\s+a)?\s*(?:euro|€)\s*(' + NUM_RE + r')', context, re.I)
            if m:
                candidates.append((it_num(m.group(1)), 0.88, context[:220]))
    # bounds + first highest confidence occurrence
    cleaned = []
    for v, conf, ev in candidates:
        if v is None:
            continue
        if lo is not None and abs(v) < lo:
            continue
        if hi is not None and abs(v) > hi:
            continue
        cleaned.append((v, conf, ev))
    if not cleaned:
        return None
    cleaned.sort(key=lambda x: x[1], reverse=True)
    v, conf, ev = cleaned[0]
    if evidence is not None and key:
        evidence[key] = {'confidence': conf, 'evidence': ev}
    return v


def extract_company_name(text, evidence=None):
    lines = _lines(text)
    for i, line in enumerate(lines):
        if _label_match(line, 'Ragione sociale') and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if len(nxt) <= 120 and re.search(r'\b(S\.?R\.?L\.?|S\.?P\.?A\.?|SOCIETA|SRL|SPA)\b', nxt, re.I):
                if evidence is not None:
                    evidence['ragione_sociale'] = {'confidence': 0.99, 'evidence': f'{line} -> {nxt}'}
                return nxt
    # Fallback: a whole line ending in company form.
    for line in lines[:80]:
        if re.search(r'\b(S\.?R\.?L\.?|S\.?P\.?A\.?|SRL|SPA)\.?$', line, re.I) and 3 < len(line) < 120:
            if evidence is not None:
                evidence['ragione_sociale'] = {'confidence': 0.82, 'evidence': line}
            return line
    return None


def extract_fields_with_meta(text):
    ev = {}
    f = {}
    f['ragione_sociale'] = extract_company_name(text, ev)
    f['ricavi_correnti'] = structured_value(text, ['Ricavi delle vendite e delle prestazioni', 'Ricavi vendite e prestazioni'], lo=1000, hi=1e12, evidence=ev, key='ricavi_correnti')
    f['risultato_netto'] = structured_value(text, ["Utile (perdita) dell'esercizio", 'Utile perdita dell esercizio'], hi=1e11, evidence=ev, key='risultato_netto')
    f['liquidita'] = structured_value(text, ['Totale disponibilita liquide', 'Disponibilita liquide', 'Disponibilità liquide'], lo=0, hi=1e12, evidence=ev, key='liquidita')
    f['debiti_banche'] = structured_value(text, ['Debiti verso banche'], lo=0, hi=1e12, evidence=ev, key='debiti_banche')
    f['debiti_altri_fin'] = structured_value(text, ['Debiti verso altri finanziatori'], lo=0, hi=1e12, evidence=ev, key='debiti_altri_fin')
    f['debito_finanziario'] = None
    if f['debiti_banche'] is not None or f['debiti_altri_fin'] is not None:
        f['debito_finanziario'] = (f['debiti_banche'] or 0) + (f['debiti_altri_fin'] or 0)
        ev['debito_finanziario'] = {'confidence': 0.97, 'evidence': 'Somma debiti verso banche + altri finanziatori'}
    f['debiti_tributari'] = structured_value(text, ['Debiti tributari'], lo=0, hi=1e12, evidence=ev, key='debiti_tributari')
    f['debiti_previdenziali'] = structured_value(text, ['Debiti verso istituti di previdenza e sicurezza sociale', 'Debiti verso istituti di previdenza', 'Debiti previdenziali'], lo=0, hi=1e12, evidence=ev, key='debiti_previdenziali')
    f['debiti_fornitori'] = structured_value(text, ['Debiti verso fornitori'], lo=0, hi=1e12, evidence=ev, key='debiti_fornitori')
    f['patrimonio_netto'] = structured_value(text, ['Totale patrimonio netto', 'Patrimonio netto'], hi=1e12, evidence=ev, key='patrimonio_netto')
    f['attivo_circolante'] = structured_value(text, ['Totale attivo circolante', 'Attivo circolante'], lo=0, hi=1e12, evidence=ev, key='attivo_circolante')
    f['passivita_correnti'] = structured_value(text, ["Debiti esigibili entro l'esercizio successivo", 'esigibili entro esercizio successivo'], lo=0, hi=1e12, evidence=ev, key='passivita_correnti')
    f['totale_debiti'] = structured_value(text, ['Totale debiti'], lo=0, hi=1e13, evidence=ev, key='totale_debiti')
    f['oneri_finanziari'] = structured_value(text, ['Interessi e altri oneri finanziari', 'Totale interessi e altri oneri finanziari'], lo=0, hi=1e11, evidence=ev, key='oneri_finanziari')

    # Prefer explicitly disclosed EBITDA/MOL. Fall back to EBIT + amortisation only if both exist.
    f['ebitda'] = structured_value(text, ['EBITDA - Margine operativo lordo', 'EBITDA', 'Margine operativo lordo'], hi=1e12, evidence=ev, key='ebitda')
    f['ebit'] = structured_value(text, ['EBIT - Risultato operativo', 'Differenza tra valore e costi della produzione', 'Risultato operativo'], hi=1e12, evidence=ev, key='ebit')
    f['ammortamenti'] = structured_value(text, ['Ammortamenti e svalutazioni', 'Totale ammortamenti e svalutazioni'], lo=0, hi=1e12, evidence=ev, key='ammortamenti')
    if f['ebitda'] is None and f['ebit'] is not None and f['ammortamenti'] is not None:
        f['ebitda'] = f['ebit'] + f['ammortamenti']
        ev['ebitda'] = {'confidence': 0.82, 'evidence': 'Ricostruito come EBIT + ammortamenti/svalutazioni'}

    quality = validate_extraction(f, ev)
    return f, {'evidence': ev, **quality}


def extract_fields(text):
    f, _ = extract_fields_with_meta(text)
    return f


def validate_extraction(f, evidence=None):
    core = ['ricavi_correnti', 'ebitda', 'debiti_tributari', 'debiti_fornitori', 'patrimonio_netto']
    useful = core + ['debito_finanziario', 'debiti_previdenziali', 'attivo_circolante', 'passivita_correnti', 'oneri_finanziari']
    found = sum(f.get(k) is not None for k in useful)
    missing_core = [k for k in core if f.get(k) is None]
    warnings = []
    if missing_core:
        warnings.append('Mancano dati essenziali: ' + ', '.join(missing_core))
    rev = f.get('ricavi_correnti')
    if rev is not None and rev <= 0:
        warnings.append('Ricavi non positivi: verificare la lettura.')
    if f.get('attivo_circolante') is not None and f.get('liquidita') is not None and f['liquidita'] > f['attivo_circolante']:
        warnings.append('Liquidità superiore all’attivo circolante: possibile errore di estrazione.')
    if f.get('debito_finanziario') is not None and f.get('debiti_banche') is not None and f.get('debiti_altri_fin') is not None:
        if abs(f['debito_finanziario'] - (f['debiti_banche'] + f['debiti_altri_fin'])) > 1:
            warnings.append('Debito finanziario non riconcilia con banche + altri finanziatori.')
    if rev and f.get('ebitda') is not None and abs(f['ebitda']) > abs(rev) * 0.8:
        warnings.append('EBITDA anomalo rispetto ai ricavi: verificare.')
    completeness = found / len(useful)
    # "Affidabile" means suitable for preliminary automatic scoring, not audited correctness.
    reliable = len(missing_core) == 0 and completeness >= 0.7 and len(warnings) <= 1
    return {'completeness': round(completeness, 2), 'missing_core': missing_core, 'warnings': warnings, 'reliable': reliable}


def clamp(v, a, b):
    return max(a, min(b, v))


def score(d, qual=None):
    q = qual or {}
    rev = d.get('ricavi_correnti')
    ebitda = d.get('ebitda')
    # Do not silently convert unavailable inputs to zero for ratios.
    tax = None if d.get('debiti_tributari') is None and d.get('debiti_previdenziali') is None else (d.get('debiti_tributari') or 0) + (d.get('debiti_previdenziali') or 0)
    fin = d.get('debito_finanziario')
    suppliers = d.get('debiti_fornitori')
    ca = d.get('attivo_circolante')
    cl = d.get('passivita_correnti')
    equity = d.get('patrimonio_netto')

    fs = 0
    if fin is not None and ebitda is not None:
        if ebitda > 0:
            lev = fin / ebitda
            fs += 5 if lev >= 6 else 4 if lev >= 4 else 3 if lev >= 3 else 1 if lev >= 1.5 else 0
        elif fin > 0:
            fs += 5
    if cl is not None and ca is not None and cl > 0 and ca / cl < 1:
        fs += 4
    if equity is not None:
        if equity < 0:
            fs += 4
        elif rev is not None and rev > 0 and equity < 0.1 * rev:
            fs += 2
    if d.get('oneri_finanziari') is not None and ebitda is not None and ebitda > 0 and d['oneri_finanziari'] > 0 and ebitda / d['oneri_finanziari'] < 1.5:
        fs += 2
    fs = clamp(fs, 0, 15)

    ts = 0
    if tax is not None and rev is not None and rev > 0:
        tr = tax / rev
        ts += 8 if tr >= 0.40 else 6 if tr >= 0.25 else 4 if tr >= 0.10 else 2 if tr >= 0.05 else 0
    if tax is not None and ebitda is not None:
        if ebitda > 0:
            te = tax / ebitda
            ts += 5 if te >= 10 else 4 if te >= 6 else 3 if te >= 3 else 1 if te >= 1 else 0
        elif tax > 0:
            ts += 5
    if tax is not None and tax > 0:
        ts += 2
    ts = clamp(ts, 0, 15)

    trs = 0
    if suppliers is not None and rev is not None and rev > 0:
        sr = suppliers / rev
        trs += 5 if sr >= 0.25 else 4 if sr >= 0.15 else 2 if sr >= 0.08 else 0
    if cl is not None and ca is not None and cl > 0 and ca / cl < 1:
        trs += 3
    if suppliers is not None and suppliers > 0:
        trs += 2
    trs = clamp(trs, 0, 10)
    comp = fs + ts + trs

    vs = 0
    if ebitda is not None and rev is not None and rev > 0 and ebitda > 0:
        margin = ebitda / rev
        vs += 8 if margin >= 0.10 else 6 if margin >= 0.05 else 4
    if d.get('risultato_netto') is not None:
        vs += 3 if d['risultato_netto'] >= 0 else 1
    vs += int(q.get('continuita', 3)) * 2
    vs = clamp(vs, 0, 20)
    restruct = clamp(int(q.get('ristrutturabilita', 3)) * 4, 0, 20)
    assets = clamp(int(q.get('asset_strategici', 3)) * 2, 0, 10)
    feas = clamp(int(q.get('fattibilita_deal', 3)) * 2, 0, 10)
    penalty = 5 if q.get('red_flag', False) else 0
    total = clamp(comp + vs + restruct + assets + feas - penalty, 0, 100)
    cls = 'A' if total >= 80 else 'B' if total >= 70 else 'C' if total >= 60 else 'D' if total >= 40 else 'E'
    fit = 'FIT-A' if ts >= 12 and vs >= 8 and restruct >= 12 and not q.get('red_flag', False) else 'FIT-B' if ts >= 8 and restruct >= 8 else 'NO-FIT'
    return {'finanziario': fs, 'fiscale': ts, 'commerciale': trs, 'composito': comp, 'continuita': vs, 'ristrutturabilita': restruct, 'asset': assets, 'fattibilita': feas, 'penalita': penalty, 'totale': round(total, 1), 'classe': cls, 'fit': fit}
