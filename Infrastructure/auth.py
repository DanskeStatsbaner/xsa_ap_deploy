from fastapi import Request, HTTPException, WebSocket, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sap import xssec

class AuthCheck(HTTPBearer):
    def __init__(self, scope: str, uaa_service: dict, auto_error: bool = True):
        super(AuthCheck, self).__init__(auto_error=auto_error)
        self.scope = scope
        self.uaa_service = uaa_service

    async def __call__(self, request: Request):
        credentials: HTTPAuthorizationCredentials = await super(AuthCheck, self).__call__(request)
        if credentials:
            if not credentials.scheme == "Bearer":
                raise HTTPException(status_code=403, detail="Invalid authentication scheme.")
            verified, security_context = verify_jwt(credentials.credentials, self.scope, self.uaa_service)
            if not verified:
                raise HTTPException(status_code=403, detail="Invalid token or expired token.")
            return security_context
        else:
            raise HTTPException(status_code=403, detail="Invalid authorization code.")

def websocket_jwt(scope, uaa_service):
    async def inner(websocket: WebSocket, jwt: str):
        verified, security_context = verify_jwt(jwt=jwt, scope=scope, uaa_service=uaa_service)
        if not verified:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return security_context if verified else None
    return inner

def verify_jwt(jwt: str, scope: str, uaa_service: dict):
    try:
        security_context = xssec.create_security_context(jwt, uaa_service)
        if scope == 'uaa.resource' or scope == 'openid':
            authorized = security_context.check_scope(scope)
        else:
            authorized = security_context.check_local_scope(scope)
        assert(authorized)
        return True, security_context
    except:
        return False, None