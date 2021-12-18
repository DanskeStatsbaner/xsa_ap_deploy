import os, json, yaml, sys
from pathlib import Path
from functools import partial
from dataclasses import dataclass, asdict
from deploy_helper import run, docker, generate_password, print, banner, get_random_bytes, AES

pwd = Path.cwd().parent
os.chdir(pwd)

docker_image = 'artifactory.azure.dsb.dk/docker/xsa_ap_cli_deploy'

###############################################################################
banner("Define functions for easier interaction with Octopus")
###############################################################################

get = lambda variable: get_octopusvariable(variable)
set = lambda variable, value, sensitive=False: set_octopusvariable(variable, str(value), sensitive)
highlight = lambda message: printhighlight(message)
fail = lambda message: failstep(message)

###############################################################################
banner("Get Octopus variables")
###############################################################################

@dataclass
class Variables:
    environment: str = get("Octopus.Environment.Name").lower()
    project_name: str = get("Octopus.Project.Name")
    release_number: str = get("Octopus.Release.Number")
    humio_ingest_token: str = get("dataART.HumioIngestToken")
    worker: str = get("Octopus.WorkerPool.Name")
    xsa_url: str = get("dataART.XSAUrl")
    xsa_user: str = get("dataART.XSAUser")
    xsa_space: str = get("dataART.XSASpace")
    xsa_keyuser: str = get("dataART.XSAKeyUser")
    xsa_pass: str = sys.argv[1]
    hana_host: str = get("dataART.Host").split('.')[0]
    hana_environment: str = get("dataART.Database").lower()
    hana_environment_upper: str = hana_environment.upper()
    artifactory_login: str = get("artifactory.login")
    artifactory_registry: str = get("artifactory.registry")
    artifactory_pass: str = sys.argv[2]
    encryption_key: bytes = get_random_bytes(32)

variables = Variables()

container_name = f"dataArt.{variables.project_name}.{variables.release_number}.{variables.environment}"

is_web = os.path.exists('xs-security.json')

###############################################################################
banner("Inject container_name into docker function")
###############################################################################

run = partial(run, worker=variables.worker, exception_handler=fail)
docker = partial(docker, container_name=container_name, exception_handler=fail)

###############################################################################
banner("Stop and delete containers")
###############################################################################

run(f'docker container stop {container_name}', ignore_errors=True)
run('docker container prune -f')

###############################################################################
banner("Log in to artifactory, pull and start docker_image")
###############################################################################

run(f'docker login -u {variables.artifactory_login} {variables.artifactory_registry} --password-stdin', env={'artifactory_pass': variables.artifactory_pass}, pipe='artifactory_pass')
run(f'docker pull {docker_image}')
run(f'docker run -v {pwd}:/data --name {container_name} --rm -t -d {docker_image}')

###############################################################################
banner("Load and modify manifest.yml from deployment")
###############################################################################

with open('manifest.yml') as manifest:
    manifest_yaml = manifest.read()

manifest_dict = yaml.safe_load(manifest_yaml)

project_type = manifest_dict['type'].lower()

if project_type != 'python':
    fail('The pipeline only supports Python XSA applications.')

services = manifest_dict['services']

host = variables.project_name.lower().replace('_', '-')
app_router = f'{variables.project_name}-sso'
app_router_host = app_router.lower().replace('_', '-')
uaa_service = f'{variables.project_name}-uaa'
url = lambda subdomain: f"https://{subdomain}.xsabi{variables.hana_environment}.dsb.dk:30033"
unprotected_url = url(host)
services += [uaa_service]

manifest_dict = {
    'applications': [
        {
            'name': variables.project_name,
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
            'destinations': json.dumps([{"name": variables.project_name, "url": unprotected_url, "forwardAuthToken": True}])
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
banner("Define environment variables for deployment")
###############################################################################

environment_variables = {
    'OCTOPUS_APP_ROUTER_URL': url(app_router_host),
    'OCTOPUS_HUMIO_INGEST_TOKEN': variables.humio_ingest_token,
    'OCTOPUS_PROJECT_NAME': variables.project_name,
    'OCTOPUS_RELEASE_NUMBER': variables.release_number,
    'OCTOPUS_APP_URL': unprotected_url
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

env = lambda d: {f'deploy_{k}'.upper(): str(v) for k, v in d.items()}

###############################################################################
banner("Deploy XSA application using XS CLI")
###############################################################################

xs_output = docker(f"python3 xs.py", env=env(asdict(variables)), work_dir='/data/octopus')

with open('xs_output.bin', 'rb') as file:
    iv = file.read(16)
    ciphered_data = file.read()

cipher = AES.new(variables.encryption_key, AES.MODE_CFB, iv=iv)
xs_output = cipher.decrypt(ciphered_data)
xs_output = json.loads(xs_output)

# Necessary, otherwise the "Scopes" variable will not be set (Octopus bug)
set("Workaround", 'Workaround')

set("Scopes", xs_output['scope'])
set("Email", xs_output['login'], True)