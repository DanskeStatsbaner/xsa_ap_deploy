from fastapi import FastAPI, Request

app = FastAPI()


@app.get(path="/", name="API Foo")
def foo():
    return {"message": "this is API Foo"}


@app.post(path="/bar", name="API Bar")
def bar():
    return {"message": "this is API Bar"}


# Using FastAPI instance
@app.get("/url-list")
def get_all_urls():
    url_list = [{"path": route.path, "name": route.name} for route in app.routes]
    return url_list


# Using Request instance
@app.get("/url-list-from-request")
def get_all_urls_from_request(request: Request):
    url_list = [
        {"path": route.path, "name": route.name} for route in request.app.routes
    ]
    return url_list


