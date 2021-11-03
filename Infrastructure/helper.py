import subprocess
from typing import Optional, List
from hdbcli.dbapi import Connection
import asyncio
from functools import partial
import json
import pandas as pd
from fastapi import WebSocket
from pydantic import BaseModel
import httpx
from env import uaa_service

def run(file_path: str, action: str, uuid: str, databases: dict = None, params: dict = None) -> str:
    try:
        uuid = '' if uuid is None else f"-u {json.dumps(uuid)}"
        databases = '' if databases is None else f"-d '{json.dumps(databases)}'"
        params = '' if params is None else f"-p '{json.dumps(params)}'"
        spawn_task = subprocess.check_output(f".buildpack/python/bin/python {file_path} {action} {uuid} {databases} {params}", stderr=subprocess.STDOUT, shell=True)
        output = spawn_task.decode("utf-8").rstrip('\n')
    except subprocess.CalledProcessError as e:
        output = e.output.decode('utf-8').rstrip('\n')

    return output

async def background_task(func, **kwargs):
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(None, partial(func, **kwargs))
    return output

def do_query(query: str, conn: Connection, access_token: Optional[str] = None) -> str:

    cursor = conn.cursor()
    if access_token is not None:
        cursor.execute(f"DO BEGIN SET 'XS_APPLICATIONUSER' = '{access_token}'; {query}; END")
    else:
        cursor.execute(query)
    columns = [c[0] for c in cursor.description]
    rows = cursor.fetchall()
    cursor.close()

    return columns, rows

class Message(BaseModel):
    content: str

class Notifier:
    def __init__(self):
        self.connections: List[WebSocket] = []
        self.generator = self.get_notification_generator()

    async def get_notification_generator(self):
        while True:
            message = yield
            await self._notify(message)

    async def push(self, msg: str):
        await self.generator.asend(msg)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def remove(self, websocket: WebSocket):
        self.connections.remove(websocket)

    async def _notify(self, message: str):
        living_connections = []
        while len(self.connections) > 0:
            # Looping like this is necessary in case a disconnection is handled
            # during await websocket.send_text(message)
            websocket = self.connections.pop()
            await websocket.send_text(message)
            living_connections.append(websocket)
        self.connections = living_connections

async def get_resource_token() -> dict:
    async with httpx.AsyncClient() as client:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        data = {
            'grant_type': 'client_credentials',
            'token_format': 'jwt'
        }
        response = await client.post(f"{uaa_service['url']}/oauth/token", headers=headers, data=data, auth=(uaa_service['clientid'], uaa_service['clientsecret']))
        return json.loads(response.text)['access_token']