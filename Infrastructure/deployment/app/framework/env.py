import yaml
from cfenv import AppEnv
from framework.auth import AuthCheck, websocket_jwt

with open('manifest') as file:
    manifest_yaml = file.read()
    manifest = yaml.safe_load(manifest_yaml)
    application = manifest['applications'][0]
    services = set(application['services'])
    containers = {service for service in services if '-uaa' not in service}
    uaa = list(services - containers)[0]
    host = application['host']
    url = 'OCTOPUS_APP_URL'

    # if it is a web app
    if len(manifest['applications']) > 1:
        app_router = manifest['applications'][1]
        secure_url = f'OCTOPUS_APP_ROUTER_URL/{host}'

env = AppEnv()

databases = {}
for container in containers:
    credentials = env.get_service(name=container).credentials
    databases[container] = dict(address=credentials['host'], port=int(credentials['port']), user=credentials['user'], password=credentials['password'])

uaa_service = env.get_service(name=uaa).credentials
auth = lambda scope: AuthCheck(scope=scope, uaa_service=uaa_service)
websocket_auth = lambda scope: websocket_jwt(scope=scope, uaa_service=uaa_service)