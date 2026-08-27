# Radar Crisi d'Impresa — Turnaround 4.2

Release 4.2 corregge i due difetti emersi nel caso pilota Casertana:

1. estrazione di numeri errati da note narrative/tabelle OCR;
2. generazione del business plan prima della chiusura della normalizzazione.

## Novità 4.2

- OCR `psm 4` per prospetti contabili e parsing page-aware.
- I valori reported sono cercati prima nei prospetti iniziali di bilancio.
- La Nota integrativa viene usata come cross-check/rescue con pattern contabili specifici.
- Controlli di coerenza: totale debiti vs componenti, importi sospetti, completezza dei core fields.
- Rettifiche evidence-based: servono evidenza esplicita di eccezionalità/non ricorrenza + importo.
- Eliminato il keyword harvesting generico che produceva falsi positivi.
- Materialità ALTA/MEDIA/BASSA.
- Stati: DA VERIFICARE / VERIFICATA / ESCLUSA.
- `Normalization Gate`: il business plan resta bloccato finché:
  - l'estrazione non è coerente;
  - esistono rettifiche materiali pendenti;
  - manca la conferma professionale.
- Nessun EBITDA margin target preimpostato all'8%: il default è il margine core normalizzato.
- Action bridge operativo obbligatoriamente visibile quando si assume un miglioramento di marginalità.
- Report Excel 4.2 con Gate, rettifiche, bridge, BP, scenari, assunzioni e piano di risanamento.

## File da caricare nel repository Streamlit

Sostituire/caricare questi file nella root del repository:

- `app.py`
- `radar_engine.py`
- `normalization_engine.py`
- `business_plan_engine.py`
- `reporting_v4.py`
- `azure_storage.py`
- `security.py`
- `requirements.txt`
- `packages.txt`

`reporting.py` può restare ma la 4.2 usa `reporting_v4.py`.

## Secrets Streamlit

Restano validi i secrets già configurati per login. Azure è opzionale:

```toml
AZURE_CONTAINER_SAS_URL = "..."
```

Non inserire credenziali nel repository.

## Workflow operativo corretto

1. Carica PDF.
2. Verifica i dati reported e le fonti mostrate dall'app.
3. Correggi eventuali estrazioni errate.
4. Chiudi ogni rettifica materiale come VERIFICATA o ESCLUSA.
5. Conferma professionalmente la base.
6. Solo a quel punto si sblocca il business plan.
7. Inserisci assunzioni e action bridge.
8. Esporta il report 4.2.

