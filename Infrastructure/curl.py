import json, subprocess, traceback, sys, requests

url = "https://ap-web-python.xsabinu0.dsb.dk:30033/scope-check"


def check_output(cmd, show_output=True, show_cmd=True):
    if show_cmd:
        print('Executing command: ', nl=False)
        print(cmd)
    popen = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            print(line, end='')
    return output
  
check_output(f'curl {url}')