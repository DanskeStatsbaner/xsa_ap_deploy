import subprocess

def run(cmd, show_output=True, show_cmd=True):
    if show_cmd:
        print('Executing command: ')
        print(cmd)
    popen = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print(line, end='')
    return output

def docker(cmd, container_name, work_dir='/', show_output=True, show_cmd=True):
    return run(f'docker exec -it {container_name} /bin/sh -c "cd {work_dir} && {cmd}"', show_output=show_output, show_cmd=show_cmd)