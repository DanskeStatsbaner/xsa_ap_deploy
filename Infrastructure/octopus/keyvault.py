import json
from hdbcli import dbapi

def keyvault(project_name, credentials, hana_host, xsa_keyuser, xsa_pass):
    hana_port = 30015

    credentials = json.dumps(credentials)
    conn = dbapi.connect(address = hana_host, port = hana_port, user = xsa_keyuser, password = xsa_pass)
    conn.cursor().execute(f"""
        UPSERT "XSA_KEY_VAULT"."XSA_KEY_VAULT.db.Tables::Key_Vault.Keys" VALUES ('{project_name}', '{credentials}') WHERE APPNAME = '{project_name}'
    """)