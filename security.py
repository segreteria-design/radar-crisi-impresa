import hmac
import time
import streamlit as st


def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def auth_configured():
    return bool(_secret('RADAR_USER')) and bool(_secret('RADAR_PASSWORD'))


def require_login():
    """Simple secrets-based gate. No credential is stored in code or target exports."""
    if not auth_configured():
        st.error('Accesso riservato non configurato.')
        st.info('Configura RADAR_USER e RADAR_PASSWORD nei Secrets dell’app Streamlit. Finché non sono presenti, il caricamento documenti resta disabilitato.')
        st.code('RADAR_USER = "nomeutente"\nRADAR_PASSWORD = "password-lunga-e-unica"', language='toml')
        st.stop()

    if st.session_state.get('_radar_auth'):
        return

    st.title('Radar Crisi d’Impresa')
    st.caption('Accesso riservato')
    attempts = int(st.session_state.get('_radar_failed', 0))
    locked_until = float(st.session_state.get('_radar_locked_until', 0))
    now = time.time()
    if locked_until > now:
        st.warning(f'Troppi tentativi. Riprova tra {int(locked_until-now)+1} secondi.')
        st.stop()

    with st.form('login_form', clear_on_submit=False):
        user = st.text_input('Utente')
        pwd = st.text_input('Password', type='password')
        submitted = st.form_submit_button('ACCEDI', use_container_width=True, type='primary')
    if submitted:
        good_user = hmac.compare_digest(user or '', str(_secret('RADAR_USER')))
        good_pwd = hmac.compare_digest(pwd or '', str(_secret('RADAR_PASSWORD')))
        if good_user and good_pwd:
            st.session_state['_radar_auth'] = True
            st.session_state['_radar_failed'] = 0
            st.rerun()
        else:
            attempts += 1
            st.session_state['_radar_failed'] = attempts
            if attempts >= 5:
                st.session_state['_radar_locked_until'] = time.time() + 30
                st.session_state['_radar_failed'] = 0
            st.error('Credenziali non valide.')
            st.stop()
    st.stop()


def logout_button():
    if st.sidebar.button('Esci'):
        for k in list(st.session_state.keys()):
            if k.startswith('_radar_auth') or k.startswith('_radar_failed') or k.startswith('_radar_locked'):
                st.session_state.pop(k, None)
        st.rerun()
