import os, subprocess, json, traceback, yaml, sys

environment = get_octopusvariable("Octopus.Environment.Name").lower()

project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"

xsa_url = get_octopusvariable("dataART.XSAUrl")
xsa_user = get_octopusvariable("dataART.XSAUser")
xsa_space = get_octopusvariable("dataART.XSASpace")
xsa_pass = sys.argv[1]

hana_environment = get_octopusvariable("dataART.Database").lower()

with open('../../manifest.yml') as manifest:
    manifest_yaml = manifest.read()
    
manifest_dict = yaml.safe_load(manifest_yaml)

project_type = manifest_dict['type']

if project_type != 'python':
    failstep('The pipeline only supports Python XSA applications.')

services = manifest_dict['services']

host = project_name.lower().replace('_', '-')
app_router = f'{project_name}-sso'
app_router_host = app_router.lower().replace('_', '-')
uaa_service = f'{project_name}-uaa'
url = lambda subdomain: f"https://{subdomain}.xsabi{hana_environment}.dsb.dk:30033"

services += [uaa_service]

manifest_dict = {
    'applications': [
        {
            'name': project_name,
            'host': host,
            'path': './app/',
            'command': 'python api.py',
            'services': services
        },
        {
            'name': app_router,
            'host': app_router_host,
            'path': './app-router/',
            'env': {
                'destinations': json.dumps([{"name": project_name, "url": url(host), "forwardAuthToken": True}])
            },
            'services': [
                uaa_service
            ]
        }
    ]
}

manifest_yaml = yaml.dump(manifest_dict)

with open('../../manifest.yml', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/manifest', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/api.py') as api:
    api_content = api.read()
    api_content = api_content.replace('OCTOPUS_APP_ROUTER_URL', url(app_router_host))

with open('../../app/api.py', 'w') as file:
    file.write(api_content)

with open('../../app-router/xs-app.json') as file:
    xs_app = json.loads(file.read())
    xs_app['welcomeFile'] = f"/{host}"
    xs_app['routes'][0]['source'] = f"/{host}(.*)"
    xs_app['routes'][0]['destination'] = project_name
    xs_app = json.dumps(xs_app, indent=2)

with open('../../app-router/xs-app.json', 'w') as file:
    file.write(xs_app)

with open('../../app-router/package.json') as file:
    package = json.loads(file.read())
    package['name'] = f"{host}-approuter"
    package = json.dumps(package, indent=2)

with open('../../app-router/package.json', 'w') as file:
    file.write(package)

hana_environment_upper = hana_environment.upper()

with open('../../xs-security.json') as file:
    xs_security = json.loads(file.read())
    xs_security['xsappname'] = project_name
    
    for index, scope in enumerate(xs_security['scopes']):
        xs_security['scopes'][index]['name'] = f'$XSAPPNAME.{scope["name"]}'
        
    scopes = [scope['name'] for scope in xs_security['scopes']]
    role_collections = []
    mappings = []

    for index, role in enumerate(xs_security['role-templates']):
        role_collection = f'{project_name}_{role["name"]}'
        role_collections += [role_collection]
        mappings += [[role_collection, f'SHIP.{hana_environment_upper}.{scope}'] for scope in role['scope-references']]
        xs_security['role-templates'][index]['name'] = f'{project_name}_{role["name"]}'
        xs_security['role-templates'][index]['scope-references'] = [f'$XSAPPNAME.{scope}' for scope in role['scope-references']]
        
    roles = [role['name'] for role in xs_security['role-templates']]

    xs_security = json.dumps(xs_security, indent=2)

with open('../../xs-security.json', 'w') as file:
    file.write(xs_security)

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

def delete_manifest():
    if os.path.exists('app/manifest'):
        os.remove('app/manifest')

check_output(f'xs login -u {xsa_user} -p {xsa_pass} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)

manifest_path = check_output(f'cd /data && find . -name manifest.yml', show_output=False, show_cmd=False)
deploy_path = os.path.dirname(manifest_path).replace('./', '')

output = check_output(f'xs service {uaa_service}', show_output=True)
xs_security = '-c xs-security.json' if os.path.exists('../../xs-security.json') else ''

if 'failed' in output:
    failstep(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and rerun xs_push.py.')
elif not 'succeeded' in output:
    output = check_output(f'cd /data/{deploy_path} && xs create-service xsuaa default {uaa_service} {xs_security}', show_output=True)
    if 'FAILED' in output:
        failstep(f'Creation of the service "{uaa_service}" failed' + '\n'.join([line for line in output.split('\n') if 'FAILED' in line]))
    else:   
        printhighlight(f'The service "{uaa_service}" was succesfully created')
else:
    output = check_output(f'cd /data/{deploy_path} && xs update-service {uaa_service} {xs_security}', show_output=True)

    if 'failed' in output:
        failstep(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and rerun xs_push.py.')
        
output = check_output(f'cd /data/{deploy_path} && xs push {app_router}')

app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + '/' + host

output = check_output(f'cd /data/{deploy_path} && xs push {project_name}')

is_running = output.rfind('RUNNING') > output.rfind('CRASHED')

if is_running:
    printhighlight(f'The application is running: {app_url}')
else:
    failstep('The application crashed')



for role_collection in role_collections:
    check_output(f'xs delete-role-collection {role_collection} -f -u {xsa_user} -p {xsa_pass}', show_cmd=False)
    check_output(f'xs create-role-collection {role_collection} -u {xsa_user} -p {xsa_pass}', show_cmd=False)
    check_output(f'xs update-role-collection {role_collection} --add-role {role_collection} -s {xsa_space} -u {xsa_user} -p {xsa_pass}', show_cmd=False)

check_output(f'docker cp cockpit.py {container_name}:/tmp/cockpit.py', docker=False)

credentials = check_output(f"python3 /tmp/cockpit.py -u {xsa_user} -p {xsa_pass} -a {xsa_url}'", show_cmd=False)
credentials = json.loads(credentials.replace('"', '\\"'))

for role_collection, attribute_value in mappings:

    body = {
        "attributeName": "Groups",
        "attributeValue": attribute_value,
        "roleCollection": role_collection,
        "operation": "equals"
    }

    cmd = f"""
        curl -s '{credentials['cockpit_url']}/ajax/samlGroupsCall/{credentials['saml_id']}' \
        -H 'X-ClientSession-Id: {credentials['session_id']}' \
        -H 'Cookie: {credentials['cookie']}' \
        -d '{json.dumps(body)}'
    """

    response = check_output(cmd, show_cmd=False, show_output=False)
    
    if response != 'null':
        failstep(f'Creation of {role_collection} -> {attribute_value} failed:\n{response}')