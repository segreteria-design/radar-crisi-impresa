# Radar Crisi d'Impresa — Web App 3.0

Versione pre-produzione con accesso riservato e privacy by design.

## File da aggiornare su GitHub
Caricare/sostituire:
- `app.py`
- `radar_engine.py`
- `security.py`
- `reporting.py`
- `requirements.txt`
- `packages.txt`

La cartella `.streamlit` contiene solo `secrets.example.toml`: **non caricare mai credenziali reali nel repository**.

## Configurazione accesso su Streamlit Community Cloud
Nella dashboard dell'app: **Settings / Impostazioni > Secrets** e inserire:

```toml
RADAR_USER = "nomeutente"
RADAR_PASSWORD = "password-lunga-e-unica"
```

Salvare. L'app si riavvia e mostra la schermata di login.

## Protezioni della 3.0
- PDF elaborato in memoria e non salvato intenzionalmente dall'app.
- Nessun archivio persistente: portafoglio solo di sessione.
- Blocco scoring su dati incompleti/anomali.
- Conferma umana obbligatoria.
- Scheda decisionale e checklist documentale automatica.

## Limite importante
Questa versione è pre-produzione. Prima di usare bilanci/documenti professionali reali, verificare privacy, DPA/condizioni hosting, localizzazione e retention dei dati, autenticazione multiutente, logging, database e backup.
