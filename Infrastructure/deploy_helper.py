import subprocess

def check_output(cmd, show_output=True, show_cmd=True, print_function=print, **print_kwargs):
    if print_function.__name__ == 'print':
        default_print_args = {'end': ''}
    if print_function.__name__ == 'echo':
        default_print_args = {'nl': False}
    print_kwargs = {**default_print_args, **print_kwargs}
    if show_cmd:
        print_function('Executing command: ')
        print_function(cmd)
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print_function(line, **print_kwargs)
    return output