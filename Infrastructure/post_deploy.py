import subprocess, sys


environment = get_octopusvariable("Octopus.Environment.Name").lower()
project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"


xsa_keyuser = get_octopusvariable("dataART.XSAKeyUser")
xsa_pass = sys.argv[1]
hana_host = get_octopusvariable("dataART.Host").split('.')[0]


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

check_output(f'docker cp keyvault.py {container_name}:/tmp/keyvault.py', docker=False)
    
check_output(f"python3 /tmp/keyvault.py -n {project_name} -h {hana_host} -u {xsa_keyuser} -p {xsa_pass}", show_cmd=False)
