from fastapi import FastAPI, Request
from fastapi.responses import Response, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from routes import router
from scope_check import scope
import uvicorn, os

app = FastAPI(redoc_url=None, docs_url=None, openapi_url=None, default_response_class=ORJSONResponse)
app.add_middleware(GZipMiddleware)
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
app.include_router(scope)

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get('PORT', 3000)), reload=True)