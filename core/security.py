from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from config import env

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    time = int(env.ACCESS_TOKEN_EXPIRE_MINUTES or 1440)
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=time)
    )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, env.JWT_SECRET_KEY, algorithm=env.JWT_ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, env.JWT_SECRET_KEY, algorithms=[env.JWT_ALGORITHM])
    return payload