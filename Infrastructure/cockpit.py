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
        click.echo('Executing command: ', nl=False)
        click.echo(click.style(cmd, fg='yellow'))
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            click.echo(line, nl=False)
    return output
  
@click.command()
@click.option('-u', '--xsa-user', required=True)
@click.option('-p', '--xsa-pass', required=True)
@click.option('-a', '--xsa-url', required=True)
def saml_role_collection(xsa_user, xsa_pass, xsa_url):
    
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

    request = driver.wait_for_request('/ajax/listSamlIDPs', timeout=120)

    session_id = request.headers['X-ClientSession-Id']
    cookie = request.headers['Cookie']

    body = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
    saml_id = body[0]['id']

    driver.quit()
    
    credentials = json.dumps({
        'cockpit_url': cockpit_url,
        'saml_id': saml_id,
        'session_id': session_id,
        'cookie': cookie
    })
    
    click.echo(credentials)

try:
    saml_role_collection()
except Exception as ex:
    click.echo(click.style(f'XSA application deployment aborted', fg='red'))
    click.echo(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))