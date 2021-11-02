from typing import Optional
from fastapi import APIRouter, Request, Depends
from framework.env import auth
import json

scope = APIRouter()

# Using Request instance
@scope.get("/url-list-from-request")
async def get_all_urls_from_request(request: Request, security_context=Depends(auth(scope='ADMIN'))):
    url_list = [
        {"path": route.path, "name": route.name} for route in request.scope.routes
    ]
    return url_list


