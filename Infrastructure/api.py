from fastapi import FastAPI, Request, File, UploadFile, Depends
from fastapi.responses import Response, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
import uvicorn, os, aiofiles
from framework.env import auth
from routes import router

app = FastAPI(redoc_url=None, docs_url=None, openapi_url=None, default_response_class=ORJSONResponse)
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
    
    protected_endpoints = {route.path: security_requirement.security_scheme.scope for route in endpoints for dependency in route.dependant.dependencies for security_requirement in dependency.security_requirements}
    
    unprotected_endpoints = {route.path: None for route in endpoints if route.path not in protected_endpoints.keys()}

    protected_websockets = {route.path: route.dependant.dependencies[0].call.keywords['scope'] for route in websockets if len(route.dependant.dependencies) > 0}
    unprotected_websockets = {route.path: None for route in websockets if len(route.dependant.dependencies) == 0}
    
    return {
        "Protected endpoints": protected_endpoints,
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



if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=int(os.environ.get('PORT', 3000)), reload=True)