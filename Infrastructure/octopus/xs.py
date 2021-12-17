import json, traceback, sys
import click
from deploy_helper import run, generate_password
from functools import partial

run = partial(run, show_output=False, show_cmd=False)

fail = print

@click.command()
@click.option('--xsa-user')
@click.option('--xsa-url')
@click.option('--xsa-space')
@click.option('--xsa-pass')
@click.option('--uaa-service')
@click.option('--is-web')
@click.option('--project-name')
@click.option('--hana-host')
@click.option('--xsa-keyuser')
@click.option('--app-router')
@click.option('--host')
@click.option('--hana-environment-upper')
@click.option('--environment')
@click.option('--unprotected-url')
def xs(xsa_user, xsa_url, xsa_space, xsa_pass, uaa_service, is_web, project_name, hana_host, xsa_keyuser, app_router, host, hana_environment_upper, environment, unprotected_url):

    is_web = bool(is_web)

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
        fail(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and restart deployment')
    elif not 'succeeded' in output:
        output = run(f'xs create-service xsuaa default {uaa_service} {xs_security}', work_dir='/data')
        if 'failed' in output:
            fail(f'Creation of the service "{uaa_service}" failed' + '\n'.join([line for line in output.split('\n') if 'FAILED' in line]))
        else:
            print(f'The service "{uaa_service}" was succesfully created')
    elif is_web:
        output = run(f'xs update-service {uaa_service} {xs_security}', work_dir='/data')

        if 'failed' in output:
            fail(f'The service "{uaa_service}" is broken. Try to delete the service with: "xs delete-service {uaa_service}" and restart deployment')

    if is_web:
        app_router_output = run(f'xs push {app_router}', work_dir='/data')

    app_output = run(f'xs push {project_name}', work_dir='/data')
    output = app_router_output if is_web else app_output


    app_url = [line.split(':', 1)[1].strip() for line in output.split('\n') if 'urls' in line][0] + (f'/{host}' if is_web else '')

    is_running = app_output.rfind('RUNNING') > app_output.rfind('CRASHED')

    if not is_running:
        fail('The application crashed')

    run(f'xs env {project_name} --export-json env.json', work_dir='/data/octopus')

    if is_web:
        for role_collection in role_collections:
            run(f'xs delete-role-collection {role_collection} -f -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
            run(f'xs create-role-collection {role_collection} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})
            run(f'xs update-role-collection {role_collection} --add-role {role_collection} -s {xsa_space} -u {xsa_user} -p $xsa_pass', env={'xsa_pass': xsa_pass})

        ad_mappings = json.dumps(ad_mappings).replace('"', '\\"')
        run(f"python3 cockpit.py -u {xsa_user} -p $xsa_pass -a {xsa_url} -m '{ad_mappings}'", env={'xsa_pass': xsa_pass}, work_dir='/data/octopus')
        set("UsersCreated", str(True))

    run(f"python3 keyvault.py -n {project_name} -h {hana_host} -u {xsa_keyuser} -p $xsa_pass", env={'xsa_pass': xsa_pass}, work_dir='/data/octopus')

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


    endpoint_collection = run(f"python3 endpoints.py -a {unprotected_url} -u $users", env={'users': json.dumps(users).replace('"', '\\"')}, work_dir='/data/octopus')
    endpoint_collection = json.loads(endpoint_collection)

try:
    xs(auto_envvar_prefix='deploy')
except Exception as ex:
    print('Something went wrong')
    print(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
    sys.exit(1)