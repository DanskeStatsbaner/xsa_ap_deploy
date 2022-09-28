from fastapi import FastAPI, Request, File, UploadFile, Depends
from fastapi.responses import Response, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
import uvicorn, os, aiofiles, traceback
from framework.env import auth
from framework.helper import humio_client
from routes import router

import logging, sys
from loguru import logger
from datetime import timedelta

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
                    "thread_name": record['thread'].name,
                    "text": message
                },
                "rawstring": record['message']
            }
        ]
    }])

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

    logger.add("api.log", rotation="1 week", enqueue=True, backtrace=True, diagnose=True)
    if os.path.exists('manifest'):
        logger.add(lambda message: humio('OCTOPUS_PROJECT_NAME', message, humio_client), format="{message}", enqueue=True, backtrace=True, diagnose=True)


app = FastAPI(redoc_url=None, docs_url=None, openapi_url=None, default_response_class=ORJSONResponse)

LOG_LEVEL = "INFO"
UVICORN_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": '%(client_addr)s - "%(request_line)s" %(status_code)s',
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

if os.path.exists('static'):
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

    # Inject access token for local development

    # access_token = '*****'

    # request.headers.__dict__["_list"].append(
    #     (
    #         "authorization".encode(),
    #         f"Bearer {access_token}".encode(),
    #     )
    # )

    response = await call_next(request)
    response.headers['Access-Control-Allow-Origin'] = ALLOWED_ORIGINS
    response.headers['Access-Control-Allow-Methods'] = ALLOWED_METHODS
    response.headers['Access-Control-Allow-Headers'] = ALLOWED_HEADERS
    return response

router = router(logger)

app.include_router(router)


@app.post("/upload")
async def upload(path: str = '', file: UploadFile=File(...), security_context=Depends(auth(scope='uaa.resource'))):
    async with aiofiles.open(f'{path}{file.filename}', 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    return {"Result": "OK"}

@app.get("/scope-check")
async def scope_check(request: Request, security_context=Depends(auth(scope='uaa.resource'))):
    endpoints = [route for route in request.app.routes if type(route) == APIRoute]
    websockets = [route for route in request.app.routes if type(route) == APIWebSocketRoute]

    to_dict = lambda endpoint, method, scope: {'endpoint': endpoint, 'method': method, 'scope': scope}

    protected_endpoints = {f'{route.path}{method}': to_dict(route.path, method, security_requirement.security_scheme.scope) for route in endpoints for dependency in route.dependant.dependencies for security_requirement in dependency.security_requirements for method in route.methods}
    unprotected_endpoints = [to_dict(route.path, method, None) for route in endpoints if f'{route.path}{"".join(route.methods)}' not in protected_endpoints.keys() for method in route.methods]

    protected_websockets = [to_dict(route.path, '-', route.dependant.dependencies[0].call.keywords['scope']) for route in websockets if len(route.dependant.dependencies) > 0]
    unprotected_websockets = [to_dict(route.path, '-', None) for route in websockets if len(route.dependant.dependencies) == 0]

    return {
        "Protected endpoints": list(protected_endpoints.values()),
        "Unprotected endpoints": unprotected_endpoints,
        "Protected websockets": protected_websockets,
        "Unprotected websockets": unprotected_websockets
    }


@app.get("/docs", include_in_schema=False)
async def get_documentation():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

@app.get("/openapi.json", include_in_schema=False)
async def openapi():
    return get_openapi(title="OCTOPUS_PROJECT_NAME", version="OCTOPUS_RELEASE_NUMBER", routes=router.routes)

@app.get("/health", include_in_schema=False)
def get_health() -> dict:
    return {"message": f"The XSA application OCTOPUS_PROJECT_NAME is running"}

if __name__ == "__main__":
    uvicorn.run(
        "api:app",
        log_config=UVICORN_LOGGING_CONFIG,
        log_level=20,
        debug='OCTOPUS_ENVIRONMENT' == 'dev',
        host="0.0.0.0",
        port=int(os.environ.get('PORT', 3000)),
        reload='OCTOPUS_ENVIRONMENT' == 'dev'
    )