# Radar Crisi d'Impresa — Turnaround 4.4

Release 4.4 corregge il parser dei PDF contabili digitali/XBRL quando il testo estratto separa la descrizione della voce dagli importi su righe successive.

## Correzioni 4.4

- Parsing multilinea delle tavole contabili: etichetta e colonne numeriche possono trovarsi su righe separate.
- I numeri di classificazione civilistica (es. `21)` o `4)`) non possono più essere scambiati per importi.
- Selezione del primo importo come esercizio corrente e del secondo come comparativo, coerentemente con le intestazioni dei prospetti.
- Preferenza per i totali contabili (`Totale debiti verso banche`, `Totale debiti`, ecc.) rispetto alle righe di dettaglio delle scadenze.
- Ragione sociale recuperata anche dall'intestazione legale del documento.
- Controlli di quadratura e plausibilità rafforzati: componenti del debito, EBITDA/valore della produzione, importi sospettosamente piccoli.
- Le passività correnti non vengono più stimate da una generica occorrenza di “esigibili entro l'esercizio successivo”: restano da verificare se manca un totale attendibile.
- Rimangono il Normalization Gate, le rettifiche evidence-based e il blocco del business plan fino a validazione professionale.

## File da caricare su GitHub/Streamlit

- `app.py`
- `radar_engine.py`
- `normalization_engine.py`
- `business_plan_engine.py`
- `reporting_v4.py`
- `azure_storage.py`
- `security.py`
- `requirements.txt`
- `packages.txt`
- `README.md`

## Test di regressione effettuato

Sul bilancio testuale LA NUOVA DFD EDILE S.R.L. 2025 il parser 4.4 ricostruisce, tra gli altri, i seguenti valori: ricavi 3.658.561; EBIT 83.250; ammortamenti materiali 121.428; EBITDA 204.678; risultato netto 16.192; liquidità 65.185; debiti bancari 344.935; debiti tributari 1.032.951; previdenziali 78.846; fornitori 1.915.615; totale debiti 3.384.775; patrimonio netto 332.948; attivo circolante 3.472.128; crediti 3.124.233; oneri finanziari 75.618.

Il business plan deve rimanere bloccato finché il professionista non convalida i dati e chiude le rettifiche materiali.


## Rafforzamenti 4.4
- parsing multilinea delle righe XBRL: il numero della voce (es. 21), 4)) non puo essere assunto come importo;
- riconciliazione automatica della cassa tra esercizio corrente e precedente;
- CFO escluso se il rendiconto riporta zero ma la variazione delle disponibilita liquide e non zero;
- controlli di quadratura su crediti, debiti, liquidita e attivo circolante prima dello sblocco del business plan.
