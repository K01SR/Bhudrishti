from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Union
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


class RoleEnum:
    STATE_ADMIN = "STATE_ADMIN"
    DISTRICT_VERIFIER = "DISTRICT_VERIFIER"
    TALUKA_VERIFIER = "TALUKA_VERIFIER"
    BUILDER = "BUILDER"
    CITIZEN = "CITIZEN"
    PUBLIC = "PUBLIC"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    jurisdiction_id: Optional[str] = None
    exp: Optional[int] = None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Any],
    role: str,
    jurisdiction_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(subject),
        "role": role,
        "jurisdiction_id": jurisdiction_id,
        "exp": expire,
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return TokenPayload(**payload)
    except (jwt.PyJWTError, ValueError):
        return None


async def get_current_user_payload(token: Optional[str] = Depends(oauth2_scheme)) -> TokenPayload:
    if not token:
        # Default unauthenticated access treated as PUBLIC role
        return TokenPayload(sub="public_anonymous", role=RoleEnum.PUBLIC)
    return await _decode_required(token)


async def get_current_user_required(token: Optional[str] = Depends(oauth2_scheme)) -> TokenPayload:
    """Depends() for write routes: rejects anonymous access (401, never PUBLIC)."""
    return await _decode_required(token)


async def _decode_required(token: Optional[str]) -> TokenPayload:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload or not payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def require_roles(allowed_roles: List[str]):
    """Role-gated dependency for state-changing routes. Anonymous never passes."""
    def role_checker(payload: TokenPayload = Depends(get_current_user_required)):
        if payload.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}, your role: {payload.role}",
            )
        return payload
    return role_checker
