# Radar Crisi d'Impresa — Turnaround 4.1

Versione 4.1: normalizzazione obbligatoria prima dei KPI, business plan 5 anni, CFADS/DSCR, stress test e piano di risanamento.

## File da caricare su Streamlit/GitHub
- `app.py`
- `radar_engine.py`
- `normalization_engine.py`
- `business_plan_engine.py`
- `reporting_v4.py`
- `security.py`
- `azure_storage.py`
- `requirements.txt`
- `packages.txt`

I moduli legacy `reporting.py` non sono necessari alla 4.1.

## Streamlit Secrets minimi
```toml
RADAR_USER = "..."
RADAR_PASSWORD = "..."
```

## Azure opzionale
Per archiviare i report sul container privato senza inserire credenziali nel repository:
```toml
AZURE_CONTAINER_SAS_URL = "https://<account>.blob.core.windows.net/<container>?<sas>"
```
Il SAS deve essere limitato al container e ai soli permessi necessari. Se il secret non è presente, l'app funziona normalmente senza archiviazione Azure.

## Metodo
- Dato reported e dato normalizzato sono sempre separati.
- Solo le rettifiche con stato `VERIFICATA` incidono su ricavi ed EBITDA.
- L'EBITDA non è preso come verità dal bilancio: quando possibile è ricostruito da EBIT + D&A, escludendo per default le svalutazioni crediti dall'add-back.
- Il business plan usa ricavi operativi normalizzati, capitale circolante, CFADS, debt service e DSCR.
