import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import Client

logger = logging.getLogger(__name__)

_DEFAULT_SECRET = "changeme-dev-only"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
if SECRET_KEY == _DEFAULT_SECRET:
    logger.warning(
        "SECRET_KEY is using the insecure default. "
        "Set the SECRET_KEY environment variable in production!"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def authenticate_client(client_key: str, password: str) -> Optional[Client]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.client_key == client_key)
        )
        client = result.scalars().first()
        if not client:
            return None
        if not verify_password(password, client.secret):
            return None
        return client


async def get_current_client(token: str) -> Optional[Client]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        client_key: str = payload.get("sub")
        if client_key is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Client).where(Client.client_key == client_key)
        )
        client = result.scalars().first()
        if client is None:
            raise credentials_exception
        return client
