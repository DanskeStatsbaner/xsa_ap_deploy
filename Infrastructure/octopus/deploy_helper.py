import subprocess, random, string, os, sys, textwrap, logging, logging.config

class _ExcludeErrorsFilter(logging.Filter):
    def filter(self, record):
        """Only returns log messages with log level below ERROR (numeric value: 40)."""
        return record.levelno < 40

config = {
    'version': 1,
    'filters': {
        'exclude_errors': {
            '()': _ExcludeErrorsFilter
        }
    },
    'formatters': {
        # Modify log message format here or replace with your custom formatter class
        'my_formatter': {
            'format': '%(message)s'
        }
    },
    'handlers': {
        'console_stderr': {
            # Sends log messages with log level ERROR or higher to stderr
            'class': 'logging.StreamHandler',
            'level': 'ERROR',
            'formatter': 'my_formatter',
            'stream': sys.stderr
        },
        'console_stdout': {
            # Sends log messages with log level lower than ERROR to stdout
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'my_formatter',
            'filters': ['exclude_errors'],
            'stream': sys.stdout
        }
    },
    'root': {
        # In general, this should be kept at 'NOTSET'.
        # Otherwise it would interfere with the log levels set for each handler.
        'level': 'NOTSET',
        'handlers': ['console_stderr', 'console_stdout']
    },
}

logging.config.dictConfig(config)

print = logging.info

def banner(title, width=70, padding=2):
    lines = []
    for line in title.split(os.linesep):
        lines += textwrap.wrap(line, width=width - padding)
    centered_lines = [f'{line:^{width}}' for line in lines]
    seperator = '#' * (width)
    print(seperator)
    print(os.linesep.join(centered_lines))
    print(seperator)

def run(cmd, env={}, pipe=None, worker=None, show_output=True, show_cmd=True, ignore_errors=False, exception_handler=None):
    if pipe is not None and pipe in env:
        variable = f'%{pipe}%' if sys.platform == 'win32' else f'${pipe}'
        cmd = f'echo {variable}| ' + cmd
    if show_cmd:
        if worker is not None:
            print(f'{worker} $ {cmd}')
        else:
            print(f'$ {cmd}')
    existing_env = os.environ.copy()
    existing_env.update(env)
    popen = subprocess.Popen(cmd, env=existing_env, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    output = ''
    while popen.poll() is None:
        line = popen.stdout.readline()
        output += line
        if show_output:
            if len(line.strip()) > 0:
                print(line)
    if not ignore_errors:
        returncode = popen.returncode
        if returncode != 0:
            message = f'The command returned an error. Return code {returncode}'
            if exception_handler is None:
                raise Exception(message)
            else:
                exception_handler(message)
    return output

def docker(cmd, container_name, env={}, pipe=None, work_dir='/', show_output=True, show_cmd=True, ignore_errors=False, exception_handler=None):
    if pipe is not None and pipe in env:
        cmd = f'echo ${pipe}| ' + cmd

    docker_variables = []
    for variable in env.keys():
        platform_variable = f'%{variable}%' if sys.platform == 'win32' else f'${variable}'
        docker_variables += [f'-e {variable}={platform_variable}']

    if show_cmd:
        print(f'docker {work_dir} $ {cmd}')

    return run(f'docker exec {" ".join(docker_variables)} -it {container_name} /bin/sh -c "cd {work_dir} && {cmd}"', env=env, show_output=show_output, show_cmd=False, ignore_errors=ignore_errors, exception_handler=exception_handler)

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