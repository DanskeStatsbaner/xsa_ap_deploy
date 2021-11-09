from fastapi import FastAPI, Request
from fastapi.responses import Response, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from routes import router
import uvicorn, os

import logging, sys
from loguru import logger
from humiolib.HumioClient import HumioIngestClient

def humio(source, message, client):
    record = message.record
    client.ingest_json_data([{
        "tags": {
            "host": "Linux VM",
            "source": source
        },
        "events": [
            {
                "timestamp": record['time'].isoformat(),
                "attributes": {
                    "elapsed": record['elapsed'] / timedelta(milliseconds=1),
                    "exception": repr(record['exception'].value) if hasattr(record['exception'], 'value') else None,
                    "traceback": repr(record['exception'].traceback) if hasattr(record['exception'], 'traceback') else None,
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
                    "thread_name": record['thread'].name
                },
                "rawstring": record['message']
            }
        ]
    }])

humio_client = HumioIngestClient(base_url= "https://cloud.humio.com", ingest_token="OCTOPUS_HUMIO_INGEST_TOKEN")
class InterceptHandler(logging.Handler):
    """
    Default handler from examples in loguru documentaion.
    See https://loguru.readthedocs.io/en/stable/overview.html#entirely-compatible-with-standard-logging
    """

    def emit(self, record: logging.LogRecord):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_level: int, json: bool):
    # intercept everything at the root logger
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(log_level)

    # remove every other logger's handlers
    # and propagate to root logger
    # noinspection PyUnresolvedReferences
    for name in logging.root.manager.loggerDict.keys():
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    # configure loguru
    logger.configure(handlers=[{"sink": sys.stdout, "serialize": json}])

    logger.add("test.log", rotation="1 week", enqueue=True, backtrace=True, diagnose=True)
    logger.add(lambda message: humio('OCTOPUS_PROJECT_NAME', message, humio_client), enqueue=True, backtrace=True, diagnose=True)


app = FastAPI(redoc_url=None, docs_url=None, openapi_url=None, default_response_class=ORJSONResponse)

LOG_LEVEL = "INFO"
UVICORN_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        },
    },
    "loggers": {
        "uvicorn": {"level": "INFO"},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"level": "INFO", "propagate": False},
    },
}

setup_logging(LOG_LEVEL, json=True)

app.add_middleware(GZipMiddleware)

if os.path.exists('/static'):
    app.mount("/static", StaticFiles(directory="static"), name="static")

ALLOWED_ORIGINS = 'OCTOPUS_APP_ROUTER_URL'
ALLOWED_METHODS = 'POST, GET, DELETE, OPTIONS'
ALLOWED_HEADERS = 'Authorization, Content-Type'

# handle CORS preflight requests
@app.options('/{rest_of_path:path}')
async def preflight_handler(request: Request, rest_of_path: str) -> Response:
    response = Response()
    response.headers['Access-Control-Allow-Origin'] = ALLOWED_ORIGINS
    response.headers['Access-Control-Allow-Methods'] = ALLOWED_METHODS
    response.headers['Access-Control-Allow-Headers'] = ALLOWED_HEADERS
    return response

# set CORS headers
@app.middleware("http")
async def add_CORS_header(request: Request, call_next):
    response = await call_next(request)
    response.headers['Access-Control-Allow-Origin'] = ALLOWED_ORIGINS
    response.headers['Access-Control-Allow-Methods'] = ALLOWED_METHODS
    response.headers['Access-Control-Allow-Headers'] = ALLOWED_HEADERS
    return response

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        log_config=UVICORN_LOGGING_CONFIG,
        log_level=20,
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get('PORT', 3000)),
        reload=True
    )