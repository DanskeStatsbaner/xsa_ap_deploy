import os, subprocess, json, yaml, sys, traceback
from pathlib import Path

def check_output(cmd, show_output=True, show_cmd=True):
    if show_cmd:
        print('Executing command: ', nl=False)
        print(cmd)
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print(line, nl=False)
    return output

environment = get_octopusvariable("Octopus.Environment.Name").lower()

if environment == 'sit':
    sys.exit(1)

print("*******************************************************************")
print(" START afload.ps1")
print("*******************************************************************")

###############################################################################
# Get all relevant parameters from octopus (variable set dataART)
###############################################################################

project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"

artifactory_login = get_octopusvariable("artifactory.login")
artifactory_registry = get_octopusvariable("artifactory.registry")
artifactory_pass = sys.argv[1]

###############################################################################
# Stop and delete containers
###############################################################################

print(container_name)

check_output(f'docker container stop {container_name}')
check_output('docker container prune -f')

###############################################################################
# Login to artifactory, pull and start XSA__AP_CLI_DEPLOY container
###############################################################################

pwd = Path.cwd().parent.parent

check_output(f'docker login -u {artifactory_login} -p {artifactory_pass} {artifactory_registry}')

check_output('docker pull artifactory.azure.dsb.dk/docker/xsa_ap_cli_deploy')
check_output(f'docker run -v {pwd}:/data --name {container_name} --rm -t -d artifactory.azure.dsb.dk/docker/xsa_ap_cli_deploy')

print("*******************************************************************")
print(" STOP afload.ps1")
print("*******************************************************************")