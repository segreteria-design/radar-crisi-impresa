# Radar Crisi d’Impresa — Web App 2.1

## Uso online
Questa cartella è pronta per Streamlit Community Cloud.
1. Caricare i file in un repository GitHub privato.
2. In Streamlit Community Cloud scegliere **Create app**.
3. Selezionare il repository e indicare `app.py` come file principale.
4. Avviare il deploy.

L'utente finale vedrà solo una pagina web: **Carica bilancio PDF → Analizza bilancio → Verifica dati → Risultato Radar**.

## Uso locale facoltativo
`pip install -r requirements.txt` e poi `streamlit run app.py`.
Serve Tesseract con lingua italiana per i PDF scansiti.

## Limiti del prototipo
- OCR e riconoscimento delle voci sono automatici ma richiedono sempre verifica umana.
- L'archivio SQLite è locale all'istanza; per produzione multiutente va sostituito con database persistente.
- Lo scoring è uno screening quantitativo/qualitativo, non una valutazione legale, fiscale o finanziaria definitiva.
