from typing import Optional
from fastapi import FastAPI, Request, Depends

scope = FastAPI()


async def common_parameters(q: Optional[str] = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}

@scope.get(path="/get", name="API get")
def get():
    return {"message": "this is API get"}


@scope.post(path="/post", name="API post")
def post():
    return {"message": "this is API post"}


# Using FastAPI instance
@scope.get("/url-list")
def get_all_urls():
    url_list = [{"path": route.path, "name": route.name} for route in scope.routes]
    return url_list

@scope.get("/items/")
async def read_items(commons: dict = Depends(common_parameters)):
    return commons

# Using Request instance
@scope.get("/url-list-from-request")
def get_all_urls_from_request(request: Request):
    url_list = [
        {"path": route.path, "name": route.name} for route in request.scope.routes
    ]
    return url_list


