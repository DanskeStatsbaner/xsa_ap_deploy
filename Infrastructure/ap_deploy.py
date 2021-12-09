import os, json, yaml, sys, traceback
from pathlib import Path
from functools import partial
from deploy_helper import run, docker

pwd = Path.cwd().parent.parent
os.chdir(pwd)

docker_image = 'artifactory.azure.dsb.dk/docker/xsa_ap_cli_deploy'

###############################################################################
#            Define functions for easier interaction with Octopus             #
###############################################################################

get = lambda variable: get_octopusvariable(variable)
set = lambda variable, value: set_octopusvariable(variable, str(value))
highlight = lambda message: printhighlight(message)
fail = lambda message: failstep(message)

###############################################################################
#                           Get Octopus variables                             #
###############################################################################

environment = get("Octopus.Environment.Name").lower()
project_name = get("Octopus.Project.Name")
release_number = get("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"
humio_ingest_token = get("dataART.HumioIngestToken")

xsa_url = get("dataART.XSAUrl")
xsa_user = get("dataART.XSAUser")
xsa_space = get("dataART.XSASpace")
xsa_keyuser = get("dataART.XSAKeyUser")
xsa_pass = sys.argv[1]

hana_host = get("dataART.Host").split('.')[0]
hana_environment = get("dataART.Database").lower()
hana_environment_upper = hana_environment.upper()

artifactory_login = get("artifactory.login")
artifactory_registry = get("artifactory.registry")
artifactory_pass = sys.argv[2]

is_web = os.path.exists('xs-security.json')

set("Web", is_web)
set("UsersCreated", False)

###############################################################################
#                 Inject container_name into docker function                  #
###############################################################################

run = partial(run, exception_handler=fail)
docker = partial(docker, container_name=container_name, exception_handler=fail)

###############################################################################
#                         Stop and delete containers                          #
###############################################################################

run(f'docker container stop {container_name}', ignore_errors=True)
run('docker container prune -f')

###############################################################################
#             Log in to artifactory, pull and start docker_image              #
###############################################################################

run(f'docker login -u {artifactory_login} {artifactory_registry} --password-stdin', env={'artifactory_pass': artifactory_pass}, pipe='artifactory_pass', show_cmd=False)
run(f'docker pull {docker_image}')
run(f'docker run -v {pwd}:/data --name {container_name} --rm -t -d {docker_image}')

###############################################################################
#                Load and modify manifest.yml from deployment                 #
###############################################################################

with open('manifest.yml') as manifest:
    manifest_yaml = manifest.read()

manifest_dict = yaml.safe_load(manifest_yaml)

project_type = manifest_dict['type'].lower()

if project_type != 'python':
    fail('The pipeline only supports Python XSA applications.')

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
        }
    ]
}

# If deployment is a web app, then append app_router part to manifest_dict
if is_web:
    manifest_dict['applications'] += [{
        'name': app_router,
        'host': app_router_host,
        'path': './app-router/',
        'env': {
            'destinations': json.dumps([{"name": project_name, "url": url(host), "forwardAuthToken": True}])
        },
        'services': [
            uaa_service
        ]
    }]
    
manifest_yaml = yaml.dump(manifest_dict)

with open('manifest.yml', 'w') as file:
    file.write(manifest_yaml)

with open('app/manifest', 'w') as file:
    file.write(manifest_yaml)

###############################################################################
#                 Define environment variables for deployment                 #
###############################################################################

environment_variables = {
    'OCTOPUS_APP_ROUTER_URL': url(app_router_host),
    'OCTOPUS_HUMIO_INGEST_TOKEN': humio_ingest_token,
    'OCTOPUS_PROJECT_NAME': project_name,
    'OCTOPUS_RELEASE_NUMBER': release_number,
    'OCTOPUS_APP_URL': url(host)
}

for variable, value in environment_variables.items():
    paths = docker(f"grep -rwl -e '{variable}'", work_dir='/data/app').strip().split('\n')
    paths = [path for path in paths if path != '']
    
    for path in paths:
        with open('app/' + path, encoding="utf-8") as file:
            content = file.read()
            content = content.replace(variable, value)

        with open('app/' + path, 'w', encoding="utf-8") as file:
            file.write(content)

###############################################################################
#                      Create files for XSA application                       #
###############################################################################

if is_web:
    with open('app-router/xs-app.json') as file:
        xs_app = json.loads(file.read())
        xs_app['welcomeFile'] = f"/{host}"
        xs_app['routes'][0]['source'] = f"/{host}(.*)"
        xs_app['routes'][0]['destination'] = project_name
        xs_app = json.dumps(xs_app, indent=2)

    with open('app-router/xs-app.json', 'w') as file:
        file.write(xs_app)

    with open('app-router/package.json') as file:
        package = json.loads(file.read())
        package['name'] = f"{host}-approuter"
        package = json.dumps(package, indent=2)

    with open('app-router/package.json', 'w') as file:
        file.write(package)

    with open('xs-security.json') as file:
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

    with open('xs-security.json', 'w') as file:
        file.write(xs_security)

###############################################################################
#                     Deploy XSA application using XS CLI                     #
###############################################################################

docker(f'xs login -u {xsa_user} -p {xsa_pass} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)

output = docker(f'xs service {uaa_service}', show_output=True).lower()

xs_security = '-c xs-security.json' if is_web else ''

if 'failed' in output:
    fail(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and rerun xs_push.py.')
elif not 'succeeded' in output:
    output = docker(f'xs create-service xsuaa default {uaa_service} {xs_security}', work_dir='/data', show_output=True)
    if 'failed' in output:
        fail(f'Creation of the service "{uaa_service}" failed' + '\n'.join([line for line in output.split('\n') if 'FAILED' in line]))
    else: 
        highlight(f'The service "{uaa_service}" was succesfully created')
else:
    output = docker(f'xs update-service {uaa_service} {xs_security}', work_dir='/data', show_output=True)

    if 'failed' in output:
        fail(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and rerun xs_push.py.')

if is_web:       
    app_router_output = docker(f'xs push {app_router}', work_dir='/data')

app_output = docker(f'xs push {project_name}', work_dir='/data')
output = app_router_output if is_web else app_output 


app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + '/' + host

is_running = app_output.rfind('RUNNING') > app_output.rfind('CRASHED')

if is_running:
    highlight(f'The application is running: {app_url}')
else:
    fail('The application crashed')

docker(f'xs env {project_name} --export-json env.json', work_dir='/data/Deployment/Scripts', show_output=True, show_cmd=True)

if is_web:  
    for role_collection in role_collections:
        docker(f'xs delete-role-collection {role_collection} -f -u {xsa_user} -p {xsa_pass}', show_cmd=False)
        docker(f'xs create-role-collection {role_collection} -u {xsa_user} -p {xsa_pass}', show_cmd=False)
        docker(f'xs update-role-collection {role_collection} --add-role {role_collection} -s {xsa_space} -u {xsa_user} -p {xsa_pass}', show_cmd=False)

    mappings = json.dumps(mappings).replace('"', '\\"')
    docker(f"python3 cockpit.py -u {xsa_user} -p {xsa_pass} -a {xsa_url} -m '{mappings}'", work_dir='/data/Deployment/Scripts', show_cmd=False)
    set("UsersCreated", str(True))

docker(f"python3 keyvault.py -n {project_name} -h {hana_host} -u {xsa_keyuser} -p {xsa_pass}", work_dir='/data/Deployment/Scripts', show_cmd=False)

with open('./Deployment/Scripts/env.json') as env_json:
    data = json.load(env_json)
    data = {key: value for key, value in data['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}
    clientid = data["clientid"]
    clientsecret = data["clientsecret"]
    url = data["url"]

credentials = run(f'curl -s -X POST {url}/oauth/token -u "{clientid}:{clientsecret}" -d "grant_type=client_credentials&token_format=jwt"')

jwt = json.loads(credentials)['access_token']

output = run(f'curl -s -X GET https://{host}.xsabi{hana_environment}.dsb.dk:30033/scope-check -H "accept: application/json" -H "Authorization: Bearer {jwt}"', show_cmd=False)

output = json.loads(output)

predefined_endpoints = [
    '/{rest_of_path:path}',
    '/docs',
    '/openapi.json',
    '/upload',
    '/scope-check',
    '/health'
]

template = ''
for title, endpoints in output.items():
    endpoints = {endpoint: scope for endpoint, scope in endpoints.items() if endpoint not in predefined_endpoints}
    if len(endpoints) > 0:
        template += f'<h3>{title}</h3>'
        template += f'<table>'
        template += f'<tr><td style="margin-right: 30px;"><strong>Endpoint</strong></td><td><strong>Scope</strong></td></tr>'
        for endpoint, scope in endpoints.items():
            template += f'<tr><td style="margin-right: 10px;">{endpoint}</td><td>{scope}</td></tr>'
        template += f'</table>'

template = template.strip()

# Necessary, otherwise the "Scopes" variable will not be set (Octopus bug)
set("Workaround", 'Workaround')

set("Scopes", template)
