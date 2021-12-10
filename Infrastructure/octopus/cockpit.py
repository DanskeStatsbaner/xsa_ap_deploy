import json, traceback, sys
from deploy_helper import run
from seleniumwire import webdriver
from seleniumwire.utils import decode
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import click

def recursive_webdriver(cockpit_url, xsa_user, xsa_pass, chromeOptions):
    driver = webdriver.Chrome(options=chromeOptions)
    driver.get(cockpit_url + '/cockpit')

    username = driver.find_element(By.NAME, 'username')
    username.send_keys(xsa_user)
    password = driver.find_element(By.NAME, 'password')
    password.send_keys(xsa_pass)

    password.submit()

    driver.get(f'{cockpit_url}/cockpit#/xsa/trustConfiguration')

    try:
        request = driver.wait_for_request('/ajax/listSamlIDPs', timeout=5)
        return driver, request
    except:
        driver.quit()
        print('Request was not found, retrying...')
        return recursive_webdriver(cockpit_url, xsa_user, xsa_pass, chromeOptions)

@click.command()
@click.option('-u', '--xsa-user', required=True)
@click.option('-p', '--xsa-pass', required=True)
@click.option('-a', '--xsa-url', required=True)
@click.option('-m', '--mappings', required=True, help=f'Mappings as JSON i.e. {json.dumps([["AP_PYTHON_WEB_ADMIN", "SHIP.NU0.DEVELOPER"], ["AP_PYTHON_WEB_USER", "SHIP.NU0.DEVELOPER"]])}')
def saml_role_collection(xsa_user, xsa_pass, xsa_url, mappings):

    mappings = json.loads(mappings)

    cockpit_url = xsa_url.replace('api', 'xsa-cockpit')

    chromeOptions = Options()
    chromeOptions.headless = True

    driver, request = recursive_webdriver(cockpit_url, xsa_user, xsa_pass, chromeOptions)

    session_id = request.headers['X-ClientSession-Id']
    cookie = request.headers['Cookie']

    body = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
    saml_id = body[0]['id']

    driver.quit()

    for role_collection, attribute_value in mappings:

        body = {
            "attributeName": "Groups",
            "attributeValue": attribute_value,
            "roleCollection": role_collection,
            "operation": "equals"
        }

        cmd = f"""
            curl -s '{cockpit_url}/ajax/samlGroupsCall/{saml_id}' \
            -H 'X-ClientSession-Id: {session_id}' \
            -H 'Cookie: {cookie}' \
            -d '{json.dumps(body)}'
        """

        response = run(cmd, show_cmd=False, show_output=False)
        if response != 'null':
            print(f'Creation of mapping {role_collection} -> {attribute_value} failed')
            sys.exit(1)
        else:
            print(f'Mapping {role_collection} -> {attribute_value} created')

try:
    saml_role_collection()
except Exception as ex:
    print(f'Something went wrong')
    print(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
    sys.exit(1)