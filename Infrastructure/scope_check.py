from fastapi import FastAPI, Request

scope = FastAPI()


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


# Using Request instance
@scope.get("/url-list-from-request")
def get_all_urls_from_request(request: Request):
    url_list = [
        {"path": route.path, "name": route.name} for route in request.scope.routes
    ]
    return url_list


