import subprocess, json, sys, os
from hdbcli import dbapi

environment = get_octopusvariable("Octopus.Environment.Name").lower()

project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"

xsa_url = get_octopusvariable("dataART.XSAUrl")
xsa_user = get_octopusvariable("dataART.XSAUser")
xsa_keyuser = get_octopusvariable("dataART.XSAKeyUser")
xsa_space = get_octopusvariable("dataART.XSASpace")
xsa_pass = sys.argv[1]

hana_environment = get_octopusvariable("dataART.Database").lower()
hana_environment_upper = hana_environment.upper()
hana_host = get_octopusvariable("dataART.Host").split('.')[0]
hana_port = 30015

def check_output(cmd, show_output=True, show_cmd=True, docker=True):
    if docker:
        cmd = f'docker exec -it {container_name} /bin/sh -c "{cmd}"'
    if show_cmd:
        print('Executing command: ')
        print(cmd)
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print(line)
    return output

#check_output(f'xs login -u {xsa_user} -p {xsa_pass} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)
#check_output(f'xs env {app_name} --export-json env.json', show_cmd=False)
def get_credentials():    
    check_output(f'xs env {project_name} --export-json env.json')

    with open('env.json', 'r') as json_file:
        data = json.load(json_file)

        data = {key: value for key, value in data['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}
       

    os.remove('env.json')

    return json.dumps(data)

#
conn = dbapi.connect(address = hana_host, port = hana_port, user = xsa_keyuser, password = xsa_pass) 
conn.cursor().execute(f"""
UPSERT "XSA_KEY_VAULT"."XSA_KEY_VAULT.db.Tables::Key_Vault.Keys" VALUES ('{project_name}', '{get_credentials()}') WHERE APPNAME = '{project_name}'
""") 
