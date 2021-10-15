from seleniumwire import webdriver
from seleniumwire.utils import decode
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from getpass import getpass
import json, subprocess, traceback
import click
from click import Abort

def check_output(cmd, show_output=True, show_cmd=True):
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
  
@click.command()
@click.option('-u', '--xsa-user', required=True)
@click.option('-p', '--xsa-pass', required=True)
@click.option('-a', '--xsa-url', required=True)
@click.option('-av', '--attribute-value', required=True)
@click.option('-rc', '--role-collection', required=True)
def saml_role_collection(xsa_user, xsa_pass, xsa_url, attribute_value, role_collection):
    
    cockpit_url = xsa_url.replace('api', 'xsa-cockpit')

    chromeOptions = Options()
    chromeOptions.headless = True
    driver = webdriver.Chrome(options=chromeOptions)
    driver.get(cockpit_url + '/cockpit')

    username = driver.find_element(By.NAME, 'username')
    username.send_keys(xsa_user)
    password = driver.find_element(By.NAME, 'password')
    password.send_keys(xsa_pass)

    password.submit()

    driver.get(f'{cockpit_url}/cockpit#/xsa/trustConfiguration')

    request = driver.wait_for_request('/ajax/listSamlIDPs')

    session_id = request.headers['X-ClientSession-Id']
    cookie = request.headers['Cookie']

    body = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
    saml_id = body[0]['id']

    driver.quit()

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

    check_output(cmd, show_cmd=False)
  
try:
    saml_role_collection()
except Exception as ex:
    click.echo(click.style(f'XSA application deployment aborted', fg='red'))
    click.echo(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))