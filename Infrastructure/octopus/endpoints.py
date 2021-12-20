import json
from deploy_helper import run
from functools import partial

run = partial(run, show_output=False, show_cmd=False)

def get_endpoints(app_url, credentials):

    credentials = run(f'curl -s -X POST $url/oauth/token -u "$clientid:$clientsecret" -d "grant_type=client_credentials&token_format=jwt"', env={"url": credentials["url"], "clientid": credentials["clientid"], "clientsecret": credentials["clientsecret"]})
    access_token = json.loads(credentials)['access_token']

    endpoint_collection = run(f'curl -s -X GET {app_url}/scope-check -H "accept: application/json" -H "Authorization: Bearer $access_token"', env={"access_token": access_token})
    endpoint_collection = json.loads(endpoint_collection)

    return endpoint_collection