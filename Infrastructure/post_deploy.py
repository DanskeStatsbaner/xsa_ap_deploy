import os, subprocess, json, traceback, yaml, sys


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

for scope in scopes:
    printhighlight(scope)

for role_collection in role_collections:
    printhighlight(role_collection)

