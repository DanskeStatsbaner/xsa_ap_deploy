import json, traceback, sys, os, ast, click
from pathlib import Path
from deploy_helper import run, generate_password
from functools import partial
from endpoints import get_endpoints
from keyvault import keyvault
from cockpit import cockpit
from Crypto.Cipher import AES

run = partial(run, show_output=True, show_cmd=True)

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
@click.option('--hana-environment-upper')
@click.option('--environment')
@click.option('--unprotected-url')
@click.option('--encryption-key')
def xs(xsa_user, xsa_url, xsa_space, xsa_pass, uaa_service, project_name, hana_host, xsa_keyuser, app_router, host, hana_environment_upper, environment, unprotected_url, encryption_key):

    encryption_key = ast.literal_eval(encryption_key)

    pwd = Path.cwd().parent
    os.chdir(pwd)

    is_web = os.path.exists('xs-security.json')

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
                ad_mappings += [[role_collection, f'SHIP.{hana_environment_upper}.{scope}'] for scope in role['scope-references']]
                scope_mappings[role_collection] = role['scope-references']
                xs_security['role-templates'][index]['name'] = f'{project_name}_{role["name"]}'
                xs_security['role-templates'][index]['scope-references'] = [f'$XSAPPNAME.{scope}' for scope in role['scope-references']]

            xs_security = json.dumps(xs_security, indent=2)

        with open('xs-security.json', 'w') as file:
            file.write(xs_security)

    run(f'xs login -u {xsa_user} -p $xsa_pass -a {xsa_url} -o orgname -s {xsa_space}', env={'xsa_pass': xsa_pass})

    output = run(f'xs service {uaa_service}').lower()

    xs_security = '-c xs-security.json' if is_web else ''

    if 'failed' in output:
        raise Exception(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and restart deployment')
    elif not 'succeeded' in output:
        output = run(f'xs create-service xsuaa default {uaa_service} {xs_security}')
        if 'failed' in output:
            raise Exception(f'Creation of the service "{uaa_service}" failed' + '\n'.join([line for line in output.split('\n') if 'FAILED' in line]))
        else:
            print(f'The service "{uaa_service}" was succesfully created')
    elif is_web:
        output = run(f'xs update-service {uaa_service} {xs_security}')

        if 'failed' in output:
            raise Exception(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and restart deployment')

    if is_web:
        app_router_output = run(f'xs push {app_router}')

    app_output = run(f'xs push {project_name}')
    output = app_router_output if is_web else app_output


    app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + (f'/{host}' if is_web else '')

    is_running = app_output.rfind('RUNNING') > app_output.rfind('CRASHED')

    if not is_running:
        raise Exception('The application crashed')

    run(f'xs env {project_name} --export-json env.json')

    with open('env.json') as env_json:
        credentials = json.load(env_json)
        credentials = {key: value for key, value in credentials['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}

    os.remove('env.json')

    if is_web:
        for role_collection in role_collections:
            run(f'xs delete-role-collection {role_collection} -f -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
            run(f'xs create-role-collection {role_collection} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
            run(f'xs update-role-collection {role_collection} --add-role {role_collection} -s {xsa_space} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})

        cockpit(xsa_user, xsa_pass, xsa_url, ad_mappings)

    keyvault(project_name, credentials, hana_host, xsa_keyuser, xsa_pass)

    if is_web:
        users = []

        # Checking User with different scopes
        for role_collection in [project_name] + role_collections:
            user = role_collection
            password = generate_password()
            scopes = scope_mappings[role_collection] if role_collection in role_collections else ['-']
            users += [(user, password, scopes)]

            # Delete existing users, to ensure that scopes are updated correctly
            if environment != 'prd':
                run(f'xs delete-user -p $xsa_pass {user} -f', env={'xsa_pass': xsa_pass})

            run(f'xs create-user {user} $password -p $xsa_pass --no-password-change', env={'password': password, 'xsa_pass': xsa_pass})
            print(f'User {user} has been created')
            if role_collection != project_name:
                run(f'xs assign-role-collection {role_collection} {user} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
                print(f'User {user} has been assiged role collection {role_collection}')

            if environment == 'prd':
                run(f'xs delete-user -p $xsa_pass {user} -f', env={'xsa_pass': xsa_pass})
                print(f'User {user} has been deleted')


    endpoint_collection = get_endpoints(unprotected_url, credentials)

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
        endpoints = {endpoint: scope for endpoint, scope in endpoints.items() if endpoint not in predefined_endpoints}
        if len(endpoints) > 0:
            scope_template += f'<h3>{title}</h3>'
            scope_template += f'<table>'
            scope_template += f'<tr><td><strong>Endpoint</strong></td><td>{table_space}</td><td><strong>Scope</strong></td></tr>'
            for endpoint, scope in endpoints.items():
                scope_template += f'<tr><td>{endpoint}</td><td>{table_space}</td><td>{scope}</td></tr>'
            scope_template += f'</table>'

    scope_template = scope_template.strip()

    login_template = ''

    if is_web:
        if environment != 'prd':
            for user, password, scopes in users:
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