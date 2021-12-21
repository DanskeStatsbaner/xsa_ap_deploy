from functools import partial
from dataclasses import dataclass
from helper import run, banner
from logger import print

banner = partial(banner, print_func=print)

###############################################################################
banner("Define functions for easier interaction with Octopus")
###############################################################################

get = lambda variable: get_octopusvariable(variable)
fail = lambda message: failstep(message)

###############################################################################
banner("Get Octopus variables")
###############################################################################

@dataclass
class Variables:
    environment: str = get("Octopus.Environment.Name").lower()
    project_name: str = get("Octopus.Project.Name")
    release_number: str = get("Octopus.Release.Number")
    worker: str = get("Octopus.WorkerPool.Name")

variables = Variables()

container_name = f"dataArt.{variables.project_name}.{variables.release_number}.{variables.environment}"

###############################################################################
banner("Inject container_name into docker function")
###############################################################################

run = partial(run, print_func=print, worker=variables.worker, exception_handler=fail)

###############################################################################
banner("Stop and delete containers")
###############################################################################

run(f'docker container stop {container_name}', ignore_errors=True)
run('docker container prune -f')