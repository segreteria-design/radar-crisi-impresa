# Radar Crisi d’impresa — Turnaround 4.5

Release di correzione del parser contabile.

## Correzione determinante

Il motore rimuove i codici di riga civilistici (`1)`, `12)`, `21)`) **prima** di leggere gli importi. Di conseguenza un codice di voce non può diventare un valore economico. Il testo PDF viene inoltre estratto con ordinamento spaziale deterministico (`sort=True`).

La schermata dell’app deve mostrare:

`Engine: 4.5-STRUCTURED-ROWS-20260827`

Se non compare questa stringa, Streamlit non sta eseguendo questi file.

## File da tenere nella root GitHub

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

Eliminare i vecchi alias italiani (`sicurezza.py`, `requisiti.txt`, `pacchetti.txt`) per evitare di distribuire moduli non allineati. La cartella `.devcontainer` può restare.

## Test di regressione

Sul file `BILANCIO+NOTA 2025.pdf` il motore deve leggere almeno: ricavi 3.658.561; EBIT 83.250; ammortamenti materiali 121.428; utile 16.192; liquidità 65.185; crediti 3.124.233; debiti banche 344.935; debiti tributari 1.032.951; previdenziali 78.846; fornitori 1.915.615; totale debiti 3.384.775; patrimonio netto 332.948; attivo circolante 3.472.128; oneri finanziari 75.618. Il CFO a zero viene rifiutato perché non riconcilia con la variazione della liquidità.
