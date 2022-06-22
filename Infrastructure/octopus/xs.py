import json, traceback, sys, os, ast, click, requests, jwt
import re
from pathlib import Path
from helper import run, generate_password, banner
from functools import partial
from cockpit import cockpit
from Crypto.Cipher import AES
from hdbcli import dbapi

# Show command and output when using the run method.
run = partial(run, show_output=True, show_cmd=True)

# As blank lines will be ignored in the log, we need to use a placeholder.
banner = partial(banner, blank_line='BLANK_LINE')

# Method for obtaining JWT.
def get_token(username, password, credentials):
    response = requests.post(
        credentials['url'] + '/oauth/token',
        data={
            "username": username,
            "password": password,
            "grant_type": "password",
            "response_type": "code",
        },
        auth=(credentials['clientid'], credentials['clientsecret'])
    )
    token = response.json()['access_token']
    return token

# Method for checking whether scopes are included in the JWT.
def check_scopes(token, scopes, project_name):
    token_scopes = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})['scope']
    app_scopes = [scope.replace(f'{project_name}.', '') for scope in token_scopes if scope.startswith(project_name)]
    return set(scopes) == set(app_scopes)

# Method for checking whether an endpoint is accesible with a given JWT.
def check_endpoint(url, method, token):
    functions = {
        'GET': requests.get,
        'POST': requests.post,
        'PATCH': requests.patch,
        'PUT': requests.put,
        'DELETE': requests.delete,
        'HEAD': requests.head
    }
    if method not in functions.keys():
        raise Exception(f'The method "{method}" is not supported by the pipeline.')
    response = functions[method](
        url,
        headers = {
            'Authorization': f'Bearer {token}'
        }
    )
    return response.status_code != 403

# The Python package `click` allows us to transform xs.py into a CLI.
# We are using auto_envvar_prefix to obtain the envirenment variables
# injected from deploy.py.
@click.command()
@click.option('--xsa-user')
@click.option('--xsa-url')
@click.option('--xsa-space')
@click.option('--xsa-pass')
@click.option('--uaa-service')
@click.option('--project-name')
@click.option('--hana-host')
@click.option('--xsa-keyuser')
@click.option('--app-router')
@click.option('--host')
@click.option('--hana-environment')
@click.option('--environment')
@click.option('--unprotected-url')
@click.option('--encryption-key')
def xs(xsa_user, xsa_url, xsa_space, xsa_pass, uaa_service, project_name, hana_host, xsa_keyuser, app_router, host, hana_environment, environment, unprotected_url, encryption_key):

    xsa_space_org = xsa_space
    xsa_space = xsa_space

    hana_port = 30015

    # Convert encryption_key from string to bytes
    encryption_key = ast.literal_eval(encryption_key)

    # As the script are executed within the /octopus directory, we need to
    # change the current directory to it's parent directory. This will
    # simplify file operations later on.
    pwd = Path.cwd().parent
    os.chdir(pwd)

    # The application is an web application if it includes a xs-security.json file.
    is_web = os.path.exists('xs-security.json')

    # If deployment is a web app, then create the necessary files for the app-router.
    # Additionally, modify the xs-security.json such that it follows the specification:
    # https://help.sap.com/products/BTP/65de2977205c403bbc107264b8eccf4b/517895a9612241259d6941dbf9ad81cb.html
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
            ad_mappings = []
            scope_mappings = {}

            for index, role in enumerate(xs_security['role-templates']):
                role_collection = f'{project_name}_{role["name"]}'
                role_collections += [role_collection]
                ad_mappings += [[role_collection, f'SHIP.{hana_environment.upper()}.{scope}'] for scope in role['scope-references']]
                scope_mappings[role_collection] = role['scope-references']
                xs_security['role-templates'][index]['name'] = f'{project_name}_{role["name"]}'
                xs_security['role-templates'][index]['scope-references'] = [f'$XSAPPNAME.{scope}' for scope in role['scope-references']]

            xs_security = json.dumps(xs_security, indent=2)

        with open('xs-security.json', 'w') as file:
            file.write(xs_security)

    ###############################################################################
    banner("Log in to SAP HANA using the XS CLI")
    ###############################################################################

    run(f'xs login -u {xsa_user} -p $xsa_pass -a {xsa_url} -o orgname -s {xsa_space}', env={'xsa_pass': xsa_pass})

    ###############################################################################
    banner("Delete existing UAA service and create a new one")
    ###############################################################################

    run(f'xs delete-service -f {uaa_service}', ignore_errors=True).lower()

    xs_security_flag = '-c xs-security.json' if is_web else ''

    uaa_service_output = run(f'xs create-service xsuaa default {uaa_service} {xs_security_flag}')
    if 'failed' in uaa_service_output:
        raise Exception(f'Creation of the service "{uaa_service}" failed' + '\n'.join([line for line in uaa_service_output.split('\n') if 'FAILED' in line]))
    else:
        print(f'The service "{uaa_service}" was succesfully created')

    if is_web:
        ###############################################################################
        banner(f"Push app router: {app_router}")
        ###############################################################################

        app_router_output = run(f'xs push {app_router}')

    ###############################################################################
    banner(f"Push app: {project_name}")
    ###############################################################################

    app_output = run(f'xs push {project_name}', ignore_errors=True)
    output = app_router_output if is_web else app_output

    app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + (f'/{host}' if is_web else '')

    is_running = app_output.rfind('RUNNING') > app_output.rfind('CRASHED')

    if not is_running:
        print('BLANK_LINE')
        run(f'xs logs {project_name} --recent')
        print('BLANK_LINE')
        raise Exception('The application crashed')

    ###############################################################################
    banner(f"Get OAuth 2.0 credentials for the app")
    ###############################################################################

    run(f'xs env {project_name} --export-json env.json')

    with open('env.json') as env_json:
        credentials = json.load(env_json)
        credentials = {key: value for key, value in credentials['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}

    os.remove('env.json')

    if is_web:
        ###############################################################################
        banner(f"Create role collections and add roles")
        ###############################################################################

        for role_collection in role_collections:
            run(f'xs delete-role-collection {role_collection} -f -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass}, ignore_errors=True)
            run(f'xs create-role-collection {role_collection} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
            run(f'xs update-role-collection {role_collection} --add-role {role_collection} -s {xsa_space} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})

        ###############################################################################
        banner(f"Assign AD groups to role collections")
        ###############################################################################

        # As XS CLI does not support AD group mapping, we need to use Selenium
        cockpit(xsa_user, xsa_pass, xsa_url, ad_mappings)

    ###############################################################################
    banner(f"Insert OAuth 2.0 credentials into XSA_KEY_VAULT")
    ###############################################################################

    xs_token = requests.post(f"{xsa_url.replace('api', 'uaa-server')}/uaa-security/oauth/token", data={'username': xsa_user, 'password': xsa_pass, 'grant_type': 'password', 'response_type': 'code'}, auth=('cf', '')).json()['access_token']

    headers = {'Authorization': f'bearer {xs_token}'}

    org_guid = requests.get(f'{xsa_url}/v2/organizations', headers=headers).json()['organizations'][0]['metadata']['guid']

    spaces = requests.get(f'{xsa_url}/v2/spaces?q=organizationGuid%3A{org_guid}', headers=headers).json()['spaces']
    space_guid = [space['metadata']['guid'] for space in spaces if space['spaceEntity']['name'] == xsa_space_org][0]

    app_name = 'XSA_KEY_VAULT-db'
    app = requests.get(f'{xsa_url}/v2/apps?q=spaceGuid%3A{space_guid}%3Bname%3A{app_name}', headers=headers).json()

    guid = app['applications'][0]['metadata']['guid']
    app_env = requests.get(f'{xsa_url}/v2/apps/{guid}/env', headers=headers).json()
    hana_credentials = json.loads(app_env['system_env_json'][0]['value'])['hana'][0]['credentials']

    xsa_key_vault_user = hana_credentials['user']
    xsa_key_vault_pass = hana_credentials['password']

    conn = dbapi.connect(address = hana_host, port = hana_port, user = xsa_key_vault_user, password = xsa_key_vault_pass)
    conn.cursor().execute(f"""
        UPSERT "XSA_KEY_VAULT"."XSA_KEY_VAULT.db.Tables::Key_Vault.Keys" VALUES ('{project_name}', '{json.dumps(credentials)}') WHERE APPNAME = '{project_name}'
    """)

    if is_web:
        ###############################################################################
        banner(f"Create XSA users for development and testing purposes")
        ###############################################################################

        users = []

        # Checking User with different scopes
        for role_collection in [project_name] + role_collections:
            username = role_collection
            password = generate_password()
            scopes = scope_mappings[role_collection] if role_collection in role_collections else []

            # Delete existing users, to ensure that scopes are updated correctly
            if environment == 'dev':
                run(f'xs delete-user -p $xsa_pass {username} -f', env={'xsa_pass': xsa_pass}, ignore_errors=True)

            run(f'xs create-user {username} $password -p $xsa_pass --no-password-change', env={'password': password, 'xsa_pass': xsa_pass})
            print(f'User {username} has been created')
            if role_collection != project_name:
                run(f'xs assign-role-collection {role_collection} {username} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
                print(f'User {username} has been assiged role collection {role_collection}')

            token = get_token(username, password, credentials)

            users += [(username, password, scopes, token)]

            if not check_scopes(token, scopes, project_name):
                raise Exception(f'{username} does not have the expected scopes. Please redeploy.')

            if environment != 'dev':
                run(f'xs delete-user -p $xsa_pass {username} -f', env={'xsa_pass': xsa_pass})
                print(f'User {username} has been deleted')

    ###############################################################################
    banner(f"Get a JWT with the uaa.resource scope")
    ###############################################################################

    access_token = json.loads(run(f'curl -s -X POST $url/oauth/token -u "$clientid:$clientsecret" -d "grant_type=client_credentials&token_format=jwt"', env={"url": credentials["url"], "clientid": credentials["clientid"], "clientsecret": credentials["clientsecret"]}, show_output=False))['access_token']

    ###############################################################################
    banner(f"Get {project_name}'s endpoints using the JWT")
    ###############################################################################

    endpoint_collection = json.loads(run(f'curl -s -X GET {unprotected_url}/scope-check -H "accept: application/json" -H "Authorization: Bearer $access_token"', env={"access_token": access_token}, show_output=False))

    predefined_endpoints = [
        '/{rest_of_path:path}',
        '/docs',
        '/openapi.json',
        '/upload',
        '/scope-check',
        '/health'
    ]

    table_space = '&nbsp;' * 10

    scope_template = ''
    for title, endpoints in endpoint_collection.items():
        if len(endpoints) > 0:
            scope_template += f'<h3>{title}</h3>'
            scope_template += f'<table>'
            scope_template += f'<tr><td><strong>Endpoint</strong></td><td>{table_space}</td><td><strong>Scope</strong></td><td>{table_space}</td><td><strong>Method</strong></td></tr>'
            for endpoint_dict in endpoints:
                endpoint, method, scope = endpoint_dict.values()
                if endpoint not in predefined_endpoints:
                    scope_template += f'<tr><td>{endpoint}</td><td>{table_space}</td><td>{scope}</td><td>{table_space}</td><td>{method}</td></tr>'
                    if 'websocket' not in title and is_web:
                        print(f'Checking {unprotected_url + endpoint}')
                        for username, _, scopes, token in users:
                            if scope in scopes:
                                if not check_endpoint(unprotected_url + endpoint, method, token):
                                    raise Exception(f'{username} could not access {endpoint}, which should be possible. Try to redeploy.')
                            else:
                                if check_endpoint(unprotected_url + endpoint, method, token):
                                    raise Exception(f'{username} could access {endpoint}, which should not be possible. Try to redeploy.')
            scope_template += f'</table>'

    scope_template = scope_template.strip()

    login_template = ''

    if is_web:
        if environment == 'dev':
            for user, password, scopes, _ in users:
                login_template += f'<table style="margin-bottom: 1rem;">'
                login_template += f'<tr><td><strong>Username</strong></td><td>{table_space}</td><td>{user}<td></tr>'
                login_template += f'<tr><td><strong>Password</strong></td><td>{table_space}</td><td>{password}<td></tr>'
                login_template += f'<tr><td><strong>Scopes</strong></td><td>{table_space}</td><td>{", ".join(scopes)}<td></tr>'
                login_template += f'</table>'

    button_style = 'color:rgb(255,255,255); text-decoration: none; font-weight: 500; padding: 8px 16px; border-radius: 5px; font-size: 18px; display: inline-block; margin-bottom: 1rem; margin-right: 1rem;'

    app_docs = unprotected_url + '/docs'

    login_template += f'<a href="{app_url}" style="background-color:rgb(68, 151, 68); {button_style}">Application</a>'
    login_template += f'<a href="{app_docs}" style="background-color:rgb(220, 149, 58); {button_style}">Documentation</a>'
    login_template = login_template.strip()

    ###############################################################################
    banner(f"Encrypt scope_template and login_template")
    ###############################################################################

    data = json.dumps({"scope": scope_template, "login": login_template}).encode('utf-8')

    cipher = AES.new(encryption_key, AES.MODE_CFB)
    ciphered_data = cipher.encrypt(data)

    with open('xs_output.bin', "wb") as file:
        file.write(cipher.iv)
        file.write(ciphered_data)

try:
    xs(auto_envvar_prefix='DEPLOY')
except Exception as ex:
    print('Something went wrong')
    print(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
    sys.exit(1)