from typing import Optional
from fastapi import APIRouter, Request, Depends
from fastapi.routing import APIRoute, APIWebSocketRoute
from framework.env import auth

scope = APIRouter()

@scope.get("/scope-check")
async def get_all_urls_from_request(request: Request, security_context=Depends(auth(scope='uaa.resource'))):
    endpoints = [route for route in request.app.routes if type(route) == APIRoute]
    websockets = [route for route in request.app.routes if type(route) == APIWebSocketRoute]
    
    protected_endpoints = {route.path: security_requirement.security_scheme.scope for route in endpoints for dependency in route.dependant.dependencies for security_requirement in dependency.security_requirements}
    
    unprotected_endpoints = {route.path: None for route in endpoints if route.path not in protected_endpoints.keys()}

    protected_websockets = {route.path: route.dependant.dependencies[0].call.keywords['scope'] for route in websockets}
    
    return [protected_endpoints, unprotected_endpoints, protected_websockets]
