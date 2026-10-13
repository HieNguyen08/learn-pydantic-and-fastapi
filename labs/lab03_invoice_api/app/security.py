"""Xác thực JWT EdDSA và Principal (Module 11). Khóa sinh lúc khởi động cho môi trường học."""
from typing import Annotated

import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, SecurityScopes
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ISSUER, AUDIENCE = "https://id.mekong.vn", "invoice-api"


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)
    sub: str
    tenant_id: int = Field(alias="tid", gt=0)
    scopes: frozenset[str] = Field(alias="scope")

    @field_validator("scopes", mode="before")
    @classmethod
    def _split(cls, v: str) -> frozenset[str]:
        return frozenset(v.split())


class KeyPair:
    def __init__(self):
        self.private = ed25519.Ed25519PrivateKey.generate()
        self.public = self.private.public_key()

    def issue(self, sub: str, tenant_id: int, scope: str, ttl: int = 600) -> str:
        import time
        now = int(time.time())
        return jwt.encode({"sub": sub, "tid": tenant_id, "scope": scope, "iss": ISSUER, "aud": AUDIENCE,
                           "iat": now, "exp": now + ttl}, self.private, algorithm="EdDSA")


bearer = HTTPBearer(auto_error=False)


async def current_principal(request: Request, security_scopes: SecurityScopes,
                            cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Principal:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "token không hợp lệ",
                                 headers={"WWW-Authenticate": "Bearer"})
    if cred is None:
        raise unauthorized
    try:
        claims = jwt.decode(cred.credentials, request.app.state.keys.public, algorithms=["EdDSA"],
                            audience=AUDIENCE, issuer=ISSUER, options={"require": ["exp", "sub", "aud", "iss"]})
        p = Principal.model_validate(claims)
    except (jwt.PyJWTError, ValidationError):
        raise unauthorized from None
    missing = set(security_scopes.scopes) - p.scopes
    if missing:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"thiếu scope: {' '.join(sorted(missing))}")
    return p
