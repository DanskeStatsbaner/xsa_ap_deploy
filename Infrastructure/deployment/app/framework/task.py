import os, traceback, argparse, json
os.environ['LOGURU_AUTOINIT'] = 'False'

from daemonocle import Daemon, expose_action
from loguru import logger
from time import sleep
from datetime import timedelta
from humiolib.HumioClient import HumioIngestClient
from pathlib import Path
from hdbcli import dbapi
from framework.env import url

class CustomDaemon(Daemon):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pid = None

    def _write_pid_file(self):
        super()._write_pid_file()
        self.pid = os.getpid()

    def _close_pid_file(self):
        super()._close_pid_file()
        self.pid = None

    @expose_action
    def status(self):
        state_file = os.path.splitext(self.pid_file)[0] + '.state'
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                status = f.readline()
                message = json.dumps({'name': self.name, 'status': status})
            self._echo(message + '\n')
            return message
        else:
            return super().status(json=True, fields=None)

    @expose_action
    def stop(self, timeout=30, force=True):
        return super().stop(timeout=timeout, force=force)

    @classmethod
    def _echo(cls, message, stderr=False, color=None):
        super()._echo(message, stderr=stderr, color=color)

    @classmethod
    def _echo_ok(cls):
        super()._echo_ok()
        logger.debug('Daemon OK')

    @classmethod
    def _echo_failed(cls):
        super()._echo_failed()
        logger.critical('Daemon failed')

    @classmethod
    def _echo_error(cls, message):
        super()._echo_error(message)
        logger.error(message)

    @classmethod
    def _echo_warning(cls, message):
        super()._echo_warning(message)
        logger.warning(message)

def exception_handler(func):
    def catch(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except Exception as ex:
            logger.critical(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
            raise Exception('Something went wrong')
    return catch

class Task:
    def __init__(self, detach=True):
        self.humio_client = HumioIngestClient(base_url= "https://cloud.humio.com", ingest_token="OCTOPUS_HUMIO_INGEST_TOKEN")
        self.task_dir = Path.cwd()
        self.log_file = 'task.log'
        self.argument_parser()
        self.uuid = self.args.uuid
        self.databases = self.args.databases
        self.daemon = CustomDaemon(
            worker=self._main,
            shutdown_callback=self._shutdown,
            name=self.uuid,
            pid_file=f'{self.task_dir}/{self.uuid}.pid',
            stderr_file=self.log_file,
            stdout_file=self.log_file,
            work_dir=self.task_dir,
            detach=detach
        )
        self.url = url
        logger.add(self.log_file, rotation="1 week")
        logger.add(lambda message: self.humio(self.log_file, message))

    def connect_db(self, container):
        container = [database for database in self.databases if container.replace('-container', '') == database.replace('-container', '')][0]
        return dbapi.connect(**self.databases[container])

    def humio(self, file, message):
        record = message.record
        self.humio_client.ingest_json_data([{
            "tags": {
                "host": "Linux VM",
                "source": file
            },
            "events": [
                {
                    "timestamp": record['time'].isoformat(),
                    "attributes": {
                        "elapsed": record['elapsed'] / timedelta(milliseconds=1),
                        "exception": record['exception'],
                        "file_name": record['file'].name,
                        "file_path": record['file'].path,
                        "function": record['function'],
                        "level": record['level'].name,
                        "line": record['line'],
                        "module": record['module'],
                        "name": record['name'],
                        "process_id": record['process'].id,
                        "process_name": record['process'].name,
                        "thread_id": record['thread'].id,
                        "thread_name": record['thread'].name,
                        "text": message.text
                    },
                    "rawstring": record['message']
                }
            ]
        }])

    def argument_parser(self):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('action', type=str, help='Action to perfom on task (start, stop, restart, status)')
        self.parser.add_argument('-u', '--uuid', type=str, help='Unique string')
        self.parser.add_argument('-p', '--params', type=json.loads, help='JSON string containing parameters')
        self.parser.add_argument('-d', '--databases', type=json.loads, help='JSON string containing database informations')
        self.args = self.parser.parse_args()

    def main(self):
        sleep(10)

    @exception_handler
    def _main(self):
        state_file = f'{self.uuid}.state'
        if os.path.exists(state_file):
            os.remove(state_file)
        logger.info(f'{self.__class__.__name__} started (UUID {self.uuid})')
        return self.main()

    def shutdown(self, message, code):
        pass

    @exception_handler
    def _shutdown(self, message, code):
        self.shutdown(message, code)
        if code == 0:
            logger.info(f'{self.__class__.__name__} completed (UUID {self.uuid})')
            with open(f'{self.uuid}.state', 'w') as f:
                f.write('completed')
        else:
            logger.critical(f'{self.__class__.__name__} failed (UUID {self.uuid})')
            with open(f'{self.uuid}.state', 'w') as f:
                f.write('failed')


    def do_action(self, action):
        self.daemon.do_action(action)
