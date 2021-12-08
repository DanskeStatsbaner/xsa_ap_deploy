import subprocess, random, string

def run(cmd, shell=False, show_output=True, show_cmd=True, ignore_errors=False):
    if show_cmd:
        print('Executing command: ')
        print(cmd)
    popen = subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print(line, end='')
    if not ignore_errors:
        returncode = popen.returncode
        if returncode != 0:
            raise Exception('The command returned an error. Return code {returncode}')
    return output

def docker(cmd, container_name, work_dir='/', show_output=True, show_cmd=True):
    return run(f'docker exec -it {container_name} /bin/sh -c "cd {work_dir} && {cmd}"', show_output=show_output, show_cmd=show_cmd)

def generate_password():
    random_source = string.ascii_letters + string.digits 
    # select 1 lowercase
    password = random.choice(string.ascii_lowercase)
    # select 1 uppercase
    password += random.choice(string.ascii_uppercase)
    # select 1 digit
    password += random.choice(string.digits)

    # generate other characters
    for i in range(8):
        password += random.choice(random_source)

    password_list = list(password)
    # shuffle all characters
    random.SystemRandom().shuffle(password_list)
    password = ''.join(password_list)
    return password