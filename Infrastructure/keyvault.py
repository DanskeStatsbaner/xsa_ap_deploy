import json, traceback, sys
import click
from hdbcli import dbapi

@click.command()
@click.option('-n', '--project-name', required=True)
@click.option('-h', '--hana-host', required=True)
@click.option('-u', '--xsa-keyuser', required=True)
@click.option('-p', '--xsa-pass', required=True)
def insert_key(project_name, hana_host, xsa_keyuser, xsa_pass):
    hana_port = 30015
    
    with open('env.json') as env_json:
        data = json.load(env_json)
        data = {key: value for key, value in data['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}
        data = json.dumps(data)
        conn = dbapi.connect(address = hana_host, port = hana_port, user = xsa_keyuser, password = xsa_pass) 
        conn.cursor().execute(f"""
            UPSERT "XSA_KEY_VAULT"."XSA_KEY_VAULT.db.Tables::Key_Vault.Keys" VALUES ('{project_name}', '{data}') WHERE APPNAME = '{project_name}'
        """) 
    
try:
    insert_key()
except Exception as ex:
    print('Something went wrong')
    print(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
    sys.exit(1)