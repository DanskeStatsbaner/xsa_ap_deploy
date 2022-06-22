import re, yaml, os
from cfenv import AppEnv
from framework.auth import AuthCheck, websocket_jwt

find_url = lambda x: [url[0] for url in re.findall(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))", x) if len(url[0]) > 0][0]

if os.path.exists('manifest'):
    with open('manifest') as file:
        manifest_yaml = file.read()
        manifest = yaml.safe_load(manifest_yaml)
        application = manifest['applications'][0]
        app_router = manifest['applications'][1]
        services = set(application['services'])
        containers = {service for service in services if '-uaa' not in service}
        uaa = list(services - containers)[0]
        url = find_url(manifest_yaml)
        host = application['host']
        secure_url = url.replace(f"{host}.", f"{app_router['host']}.") + f'/{host}'
else:
    with open('../manifest.yml') as file:
        manifest_yaml = file.read()
        manifest = yaml.safe_load(manifest_yaml)
        containers = manifest['services']
        uaa = None

env = AppEnv()

databases = {}
for container in containers:
    service = env.get_service(name=container)
    if service is not None:
        credentials = service.credentials
        databases[container] = dict(address=credentials['host'], port=int(credentials['port']), user=credentials['user'], password=credentials['password'])
    else:
        # TO DO: Collect container credentials using XS CLI and HANA API endpoints
        databases[container] = {}

service = env.get_service(name=uaa)
if service is not None:
    uaa_service = service.credentials
else:
    # TO DO: Collect uaa service credentials using XS CLI and HANA API endpoints
    uaa_service = {}

auth = lambda scope: AuthCheck(scope=scope, uaa_service=uaa_service)
websocket_auth = lambda scope: websocket_jwt(scope=scope, uaa_service=uaa_service)