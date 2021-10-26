import subprocess, json, click, traceback
from hdbcli import dbapi


def check_output(cmd, show_output=True, show_cmd=True):
    if show_cmd:
        click.echo('Executing command: ', nl=False)
        click.echo(click.style(cmd, fg='yellow'))
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            click.echo(line, nl=False)
    return output
  
@click.command()
@click.option('-n', '--project-name', required=True)
@click.option('-h', '--hana-host', required=True)
@click.option('-u', '--xsa-keyuser', required=True)
@click.option('-p', '--xsa-pass', required=True)

def insert_key(project_name,hana_host,xsa_keyuser,xsa_pass):
    hana_port = 30015
   
    check_output(f'xs env {project_name} --export-json env.json')
    env_json = check_output(f'cat env.json')

    data = json.load(env_json)
    data = {key: value for key, value in data['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}
   
    conn = dbapi.connect(address = hana_host, port = hana_port, user = xsa_keyuser, password = xsa_pass) 
    conn.cursor().execute(f"""
        UPSERT "XSA_KEY_VAULT"."XSA_KEY_VAULT.db.Tables::Key_Vault.Keys" VALUES ('{project_name}', '{data}') WHERE APPNAME = '{project_name}'
    """) 
    
try:
    insert_key()
except Exception as ex:
    click.echo(click.style(f'Something went wrong', fg='red'))
    click.echo(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))