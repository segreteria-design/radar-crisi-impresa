"""Optional Azure Blob archiving. The app works without Azure secrets.
Recommended secret: AZURE_CONTAINER_SAS_URL, scoped to the private container with only required permissions.
"""
import datetime
import streamlit as st


def configured():
    try:
        return bool(st.secrets.get('AZURE_CONTAINER_SAS_URL'))
    except Exception:
        return False


def upload_bytes(name,data,content_type='application/octet-stream'):
    if not configured():
        return False,'Azure archiving not configured'
    from azure.storage.blob import ContainerClient, ContentSettings
    url=st.secrets['AZURE_CONTAINER_SAS_URL']
    c=ContainerClient.from_container_url(url)
    blob=c.get_blob_client(name)
    blob.upload_blob(data,overwrite=True,content_settings=ContentSettings(content_type=content_type))
    return True,name


def dated_name(prefix,filename):
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    safe=''.join(ch if ch.isalnum() or ch in '._-' else '_' for ch in filename)
    return f'{prefix}/{stamp}_{safe}'
