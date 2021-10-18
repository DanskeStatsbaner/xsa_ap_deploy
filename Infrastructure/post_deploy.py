import os, subprocess, json, traceback, yaml, sys
from ap_deploy import check_output, project_name, xsa_url, xsa_user, xsa_space, xsa_pass, hana_environment_upper

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

check_output(f'xs login -u {xsa_user} -p {xsa_pass} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)

for role_collection in role_collections:
    user = role_collection
    password = 'A1a' + role_collection
    check_output(f' xs create-user -p {xsa_pass} {user} {password}',show_output=True, show_cmd=True)
    printhighlight(f'User {user} has been created')
    check_output(f' xs assign-role-collection -p {xsa_pass} {role_collection} {user}' ,show_output=True, show_cmd=True)
    printhighlight(f'User {user} has been assiged role collection {role_collection}')
    # Insert endpoint check below    
    if 1==0:    
        check_output(f' xs delete-user -p {xsa_pass} {user} {password}',show_output=True, show_cmd=True)
        printhighlight(f'User {user} has been deleted')
    # exit
    else:
        check_output(f' xs delete-user -p {xsa_pass} {user} {password}',show_output=True, show_cmd=True)
        printhighlight(f'User {user} has been deleted')



