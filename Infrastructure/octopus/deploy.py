import os, json, yaml, sys
from pathlib import Path
from functools import partial
from dataclasses import dataclass, asdict
from helper import run, docker, banner, generate_encryption_key
from Crypto.Cipher import AES
from logger import print

# Inject the print method from the logger module into the banner method
banner = partial(banner, print_func=print)

# As the script are executed within the /octopus directory, we need to
# change the current directory to it's parent directory. This will
# simplify file operations later on.
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

#@dataclass - disable dataclass for Python 3.6
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
    artifactory_login: str = get("artifactory.login")
    artifactory_registry: str = get("artifactory.registry")
    artifactory_pass: str = sys.argv[2]
    encryption_key: bytes = generate_encryption_key()

    # The following variables will be set later
    uaa_service: str = None
    app_router: str = None
    host: str = None
    unprotected_url: str = None

variables = Variables()

container_name = f"dataArt.{variables.project_name}.{variables.release_number}.{variables.environment}"

# The application is an web application if it includes an xs-security.json file
is_web = os.path.exists('xs-security.json')

###############################################################################
banner("Inject container_name into docker function")
###############################################################################

run = partial(run, print_func=print, worker=variables.worker, exception_handler=fail)
docker = partial(docker, print_func=print, container_name=container_name, exception_handler=fail)

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

# It's necessary to modify the manifest.yml before we can push the application
# to HANA. Examples of manifest.yml files can be found here:
# https://github.com/saphanaacademy/XSUAA/

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

variables.uaa_service = uaa_service
variables.app_router = app_router
variables.host = host
variables.unprotected_url = unprotected_url

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

# Define "environment variables" for the deployment. Each variable will be
# injected into the source code of the deployment.
# TO DO: Use xs set-env instead of modifying the source code.

environment_variables = {
    'OCTOPUS_APP_ROUTER_URL': url(app_router_host),
    'OCTOPUS_HUMIO_INGEST_TOKEN': variables.humio_ingest_token,
    'OCTOPUS_PROJECT_NAME': variables.project_name,
    'OCTOPUS_RELEASE_NUMBER': variables.release_number,
    'OCTOPUS_APP_URL': unprotected_url,
    'OCTOPUS_XSA_SPACE': variables.xsa_space
}

for variable, value in environment_variables.items():
    paths = docker(f"grep -rwl -e '{variable}'", work_dir='/data/app', ignore_errors=True).strip().split('\n')
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

# Execute xs.py on the docker container, this allows us to use external python
# modules instead of relying on standard modules. In addition, it simplifies
# exception handling.
xs_output = docker(f"python3 xs.py", env=env(asdict(variables)), work_dir='/data/octopus')

###############################################################################
banner("Decrypt the encrypted files created by xs.py")
###############################################################################

with open('xs_output.bin', 'rb') as file:
    iv = file.read(16)
    ciphered_data = file.read()

cipher = AES.new(variables.encryption_key, AES.MODE_CFB, iv=iv)
xs_output = cipher.decrypt(ciphered_data)
xs_output = json.loads(xs_output)

# Necessary, otherwise the "Scopes" variable will not be set (Octopus bug).
set("Workaround", 'Workaround')

# Set Octopus variables which is used in the mails send to the developer.
set("Scopes", xs_output['scope'])
set("Email", xs_output['login'], True)