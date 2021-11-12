import json, string, random, sys, os
from deploy_helper import check_output

environment = get_octopusvariable("Octopus.Environment.Name").lower()
project_name = get_octopusvariable("Octopus.Project.Name")
release_number = get_octopusvariable("Octopus.Release.Number")
container_name = f"dataArt.{project_name}.{release_number}.{environment}"

xsa_url = get_octopusvariable("dataART.XSAUrl")
xsa_user = get_octopusvariable("dataART.XSAUser")
xsa_space = get_octopusvariable("dataART.XSASpace")
xsa_pass = sys.argv[1]

hana_environment = get_octopusvariable("dataART.Database").lower()
hana_environment_upper = hana_environment.upper()

is_web = os.path.exists('../../xs-security.json')

check_output = lambda cmd, show_output=True, show_cmd=True, docker=True: check_output(f'docker exec -it {container_name} /bin/sh -c "{cmd}"' if docker else cmd, show_output, show_cmd)

def get_random_password():
    random_source = string.ascii_letters + string.digits 
    # select 1 lowercase
    password = random.choice(string.ascii_lowercase)
    # select 1 uppercase
    password += random.choice(string.ascii_uppercase)
    # select 1 digit
    password += random.choice(string.digits)
    # select 1 special symbol
    # password += random.choice(string.punctuation)

    # generate other characters
    for i in range(8):
        password += random.choice(random_source)

    password_list = list(password)
    # shuffle all characters
    random.SystemRandom().shuffle(password_list)
    password = ''.join(password_list)
    return password

#check_output(f'xs login -u {xsa_user} -p {xsa_pass} -a {xsa_url} -o orgname -s {xsa_space}', show_cmd=False)

#Checking User without scope
if is_web:
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
    
    users = []
    
    # Checking User with different scopes
    for role_collection in [project_name] + role_collections:
        user = role_collection
        password = get_random_password()
        users += [(user, password)]
        
        if environment == 'dev':
            check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=False)
        
        check_output(f'xs create-user  {user} {password} -p {xsa_pass} --no-password-change',show_output=True, show_cmd=False)
        printhighlight(f'User {user} has been created')
        if role_collection != project_name:
            check_output(f'xs assign-role-collection {role_collection} {user} -u {xsa_user} -p {xsa_pass}', show_output=True, show_cmd=False)
            printhighlight(f'User {user} has been assiged role collection {role_collection}')
        
        if environment != 'dev':
            check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=False)
            printhighlight(f'User {user} has been deleted')
    
    if environment == 'dev':
        
        template = ''
        for user, password in users:
            template += f"<table>"
            template += f"<tr><td><strong>Username</strong></td><td>{user}<td></tr>"
            template += f"<tr><td><strong>Password</strong></td><td>{password}<td></tr>"
            template += f"</table>"
       
        set_octopusvariable("Users", template.strip(), True)