import os, subprocess, json, traceback, re, yaml, sys

environment = get_octopusvariable("Octopus.Environment.Name").lower()

project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"

xsa_url = get_octopusvariable("dataART.XSAUrl")
xsa_user = get_octopusvariable("dataART.XSAUser")
xsa_space = get_octopusvariable("dataART.XSASpace")

hana_environment = get_octopusvariable("dataART.Database").lower()

XSAPW = sys.argv[1]

find_url = lambda x: [url[0] for url in re.findall(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))", x) if len(url[0]) > 0][0]

with open('../../manifest.yml') as manifest:
    manifest_yaml = manifest.read()
    manifest_dict = yaml.safe_load(manifest_yaml)
    application = manifest_dict['applications'][0]
    app_router = manifest_dict['applications'][1]
    app_name = application['name']
    app_router_name = app_router['name']

    destinations = json.loads(app_router['env']['destinations'])
    destinations[0]['name'] = app_name
    url = destinations[0]['url'].replace('nu0.dsb.dk', f'{hana_environment}.dsb.dk')
    host = url.replace('https://', '').split('.')[0]
    destinations[0]['url'] = url.replace(f'{host}.', f'{application["host"]}.')
    manifest_dict['applications'][1]['env']['destinations'] = json.dumps(destinations)

    manifest_yaml = yaml.dump(manifest_dict)

with open('../../manifest.yml', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/manifest', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/api.py') as api:
    api_content = api.read()
    app_router_url = find_url(api_content)
    api_content = api_content.replace(app_router_url, url.replace(f'{host}.', f'{app_router_name}.'))

with open('../../app/api.py', 'w') as file:
    file.write(api_content)

with open('../../app-router/xs-app.json') as file:
    xs_app = json.loads(file.read())
    xs_app['welcomeFile'] = f"/{application['host']}"
    xs_app['routes'][0]['source'] = f"/{application['host']}(.*)"
    xs_app['routes'][0]['destination'] = app_name
    xs_app = json.dumps(xs_app, indent=2)

with open('../../app-router/xs-app.json', 'w') as file:
    file.write(xs_app)

with open('../../app-router/package.json') as file:
    package = json.loads(file.read())
    package['name'] = f"{app_name}-approuter"
    package = json.dumps(package, indent=2)

with open('../../app-router/package.json', 'w') as file:
    file.write(package)

hana_environment_upper = hana_environment.upper()

with open('../../xs-security.json') as file:
    xs_security = json.loads(file.read())
    xs_security['xsappname'] = app_name
    
    for index, scope in enumerate(xs_security['scopes']):
        xs_security['scopes'][index]['name'] = f'$XSAPPNAME.{project_name}_{scope["name"]}'
        
    scopes = [scope['name'] for scope in xs_security['scopes']]
    role_collections = []

    for index, role in enumerate(xs_security['role-templates']):
        role_collections += [f'{project_name}_{role["name"]}']
        xs_security['role-templates'][index]['name'] = f'{project_name}_{role["name"]}'
        xs_security['role-templates'][index]['scope-references'] = [f'$XSAPPNAME.{project_name}_{scope}' for scope in role['scope-references']]
        
    roles = [role['name'] for role in xs_security['role-templates']]
    
    xs_security = json.dumps(xs_security, indent=2)

with open('../../xs-security.json', 'w') as file:
    file.write(xs_security)

uaa = [service for service in application['services'] if '-uaa' in service][0]

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

check_output(f'xs login -u {xsa_user} -p {XSAPW} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)

manifest_path = check_output(f'cd /data && find . -name manifest.yml', show_output=False, show_cmd=False)
deploy_path = os.path.dirname(manifest_path).replace('./', '')

output = check_output(f'xs service {uaa}', show_output=True)
xs_security = '-c xs-security.json' if os.path.exists('../../xs-security.json') else ''

if 'failed' in output:
    failstep(f'The service "{uaa}" is broken. Try to delete the service with: "xs delete-service {uaa}" and rerun xs_push.py.')
elif not 'succeeded' in output:
    output = check_output(f'cd /data/{deploy_path} && xs create-service xsuaa default {uaa} {xs_security}', show_output=True)
    if 'FAILED' in output:
        failstep(f'Creation of the service "{uaa}" failed' + '\n'.join([line for line in output.split('\n') if 'FAILED' in line]))
    else:   
        printhighlight(f'The service "{uaa}" was succesfully created')
else:
    output = check_output(f'cd /data/{deploy_path} && xs update-service {uaa} {xs_security}', show_output=True)

    if 'failed' in output:
        failstep(f'The service "{uaa}" is broken. Try to delete the service with: "xs delete-service {uaa}" and rerun xs_push.py.')
        
output = check_output(f'cd /data/{deploy_path} && xs push {app_router_name}')

app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + '/' + app_name

output = check_output(f'cd /data/{deploy_path} && xs push {app_name}')

is_running = output.rfind('RUNNING') > output.rfind('CRASHED')

if is_running:
    printhighlight(f'The application is running: {app_url}')
else:
    failstep('The application crashed')


printhighlight(check_output(f'xs roles web -s {xsa_space} -u {xsa_user} -p {XSAPW}', show_cmd=False))
printhighlight(check_output(f'xs role-templates web -s {xsa_space} -u {xsa_user} -p {XSAPW}', show_cmd=False))
printhighlight(check_output(f'xs role User -s {xsa_space} -u {xsa_user} -p {XSAPW}', show_cmd=False))
printhighlight(check_output(f'xs role-collections -u {xsa_user} -p {XSAPW}', show_cmd=False))
printhighlight(check_output(f'xs assigned-role-collections MILIMAT0810 -u {xsa_user} -p {XSAPW}', show_cmd=False))


for role_collection in role_collections:
    printhighlight(check_output(f'xs create-role-collection {role_collection} -u {xsa_user} -p {XSAPW}', show_cmd=False))

for role_collection in role_collections:
    for role in roles:
        printhighlight(check_output(f'xs update-role-collection {role_collection} --add-role {role} --app {project_name} -s {xsa_space} -t {role} -u {xsa_user} -p {XSAPW}', show_cmd=False))