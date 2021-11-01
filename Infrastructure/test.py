import subprocess, json, string, random

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

is_web = os.path.exists('../../app-router')

mail = get_octopusvariable("Octopus.Deployment.CreatedBy.EmailAddress")
printhighlight(mail)
created_by_username = get_octopusvariable("Octopus.Deployment.CreatedBy.Username").split('@')[0]
printhighlight(created_by_username)

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
    

    user = project_name

    check_output(f'xs create-user -p {xsa_pass} {user} {get_random_password()} -f',show_output=True, show_cmd=True)
    printhighlight(f'User {user} has been created')
    if 1==0:    
        check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=True)
        printhighlight(f'User {user} has been deleted')
        # exit
    else:
        check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=True)
        printhighlight(f'User {user} has been deleted')


    # Checking User with different scopes
    for role_collection in role_collections:
        user = role_collection
        check_output(f'xs create-user  {user} {get_random_password()} -p {xsa_pass}',show_output=True, show_cmd=True)
        printhighlight(f'User {user} has been created')
        check_output(f'xs assign-role-collection {role_collection} {user} -u {xsa_user} -p {xsa_pass}' ,show_output=True, show_cmd=False)
        printhighlight(f'User {user} has been assiged role collection {role_collection}')
        # Insert endpoint check below    
        if 1==0:    
            check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=True)
            printhighlight(f'User {user} has been deleted')
        # exit
        else:
            check_output(f'xs delete-user -p {xsa_pass} {user} -f',show_output=True, show_cmd=True)
            printhighlight(f'User {user} has been deleted')
    
    if environment == 'dev':
        
        template = ''

               
        

        for role_collection in role_collections:  
            user = role_collection   
            #password = get_random_password()
            password = 'Pass1234'                            
            check_output(f'xs create-user {user} {password} -p {xsa_pass} --no-password-change',show_output=True, show_cmd=False)   
            check_output(f'xs assign-role-collection {role_collection} {user} -u {xsa_user} -p {xsa_pass}' ,show_output=True, show_cmd=False)
            #check_output(f'xs assign-role-collection XS_CONTROLLER_USER {user} -u {xsa_user} -p {xsa_pass}' ,show_output=True, show_cmd=False)
            template += f"""
            Username: {role_collection}
            Password: {password}
            """
            # Insert endpoint check below 
    printhighlight(template) 
       
    set_octopusvariable("Users", template, True)