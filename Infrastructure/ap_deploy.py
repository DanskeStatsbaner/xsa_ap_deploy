import os, subprocess, json, traceback, re, yaml, sys

environment = get_octopusvariable("Octopus.Environment.Name")

projectName = get_octopusvariable("Octopus.Project.Name")
releaseNumber = get_octopusvariable("Octopus.Release.Number")
containerName = f"dataArt.{projectName}.{releaseNumber}.{environment}"

XSAurl = get_octopusvariable("dataART.XSAUrl")
XSAuser = get_octopusvariable("dataART.XSAUser")
XSAspace = get_octopusvariable("dataART.XSASpace")
XSAPW = sys.argv[1]

find_url = lambda x: [url[0] for url in re.findall(r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))", x) if len(url[0]) > 0][0]

with open('../../manifest.yml') as manifest:
    manifest_yaml = manifest.read()
    manifest_dict = yaml.safe_load(manifest_yaml)
    application = manifest_dict['applications'][0]
    app_router = manifest_dict['applications'][1]
    app_name = application['name']
    app_router_name = app_router['name']

    destinations = json.loads(app_router['env']['destinations'])
    destinations[0]['name'] = app_name
    url = destinations[0]['url']
    host = url.replace('https://', '').split('.')[0]
    destinations[0]['url'] = url.replace(f'{host}.', f'{application["host"]}.')
    manifest_dict['applications'][1]['env']['destinations'] = json.dumps(destinations)

    manifest_yaml = yaml.dump(manifest_dict)

with open('../../manifest.yml', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/manifest', 'w') as file:
    file.write(manifest_yaml)

with open('../../app/api.py') as api:
    api_content = api.read()
    app_router_url = find_url(api_content)
    api_content = api_content.replace(app_router_url, url.replace(f'{host}.', f'{app_router_name}.'))

with open('../../app/api.py', 'w') as file:
    file.write(api_content)

with open('../../app-router/xs-app.json') as file:
    xs_app = json.loads(file.read())
    xs_app['welcomeFile'] = f"/{application['host']}"
    xs_app['routes'][0]['source'] = f"/{application['host']}(.*)"
    xs_app['routes'][0]['destination'] = app_name
    xs_app = json.dumps(xs_app, indent=2)

with open('../../app-router/xs-app.json', 'w') as file:
    file.write(xs_app)

with open('../../app-router/package.json') as file:
    package = json.loads(file.read())
    package['name'] = f"{app_name}-approuter"
    package = json.dumps(package, indent=2)

with open('../../app-router/package.json', 'w') as file:
    file.write(package)

with open('../../xs-security.json') as file:
    xs_security = json.loads(file.read())
    xs_security['xsappname'] = app_name
    xs_security = json.dumps(xs_security, indent=2)

with open('../../xs-security.json', 'w') as file:
    file.write(xs_security)

uaa = [service for service in application['services'] if '-uaa' in service][0]

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

def delete_manifest():
    if os.path.exists('app/manifest'):
        os.remove('app/manifest')

manifest_path = check_output(f'docker exec -it {containerName} /bin/sh -c "cd /data && find . -name manifest.yml"', True, True)

print(manifest_path)

check_output(f'docker exec -it {containerName} /bin/sh -c "cd /data && ls -a && xs login -u {XSAuser} -p {XSAPW} -a {XSAurl} -o orgname -s {XSAspace} && xs push {app_name} > /data/{containerName}.log"', True, False)



print(environment)
print(projectName)
print(releaseNumber)
print(containerName)
print(XSAurl)
print(XSAuser)
print(XSAspace)