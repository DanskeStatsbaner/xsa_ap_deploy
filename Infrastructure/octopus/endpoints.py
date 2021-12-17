import json
from deploy_helper import run
from functools import partial

run = partial(run, show_output=False, show_cmd=False)

def get_endpoints(app_url, users):
    users = json.loads(users)
    with open('env.json') as env_json:
        data = json.load(env_json)
        data = {key: value for key, value in data['VCAP_SERVICES']['xsuaa'][0]['credentials'].items() if key in ['clientid', 'clientsecret', 'url']}
        clientid = data["clientid"]
        clientsecret = data["clientsecret"]
        url = data["url"]

    credentials = run(f'curl -s -X POST $url/oauth/token -u "$clientid:$clientsecret" -d "grant_type=client_credentials&token_format=jwt"', env={"url": url, "clientid": clientid, "clientsecret": clientsecret})
    access_token = json.loads(credentials)['access_token']

    endpoint_collection = run(f'curl -s -X GET {app_url}/scope-check -H "accept: application/json" -H "Authorization: Bearer $access_token"', env={"access_token": access_token})

    return endpoint_collection