import base64
from datetime import datetime, timedelta
from typing import Optional, Any, Union
from jose import jwt
from passlib.context import CryptContext
from app.core.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ALGORITHM is now pulled from settings to ensure consistency
ALGORITHM = settings.auth.algorithm
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = settings.auth.access_token_expire_minutes
except:
    ACCESS_TOKEN_EXPIRE_MINUTES = 30 # Fallback

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    
    # Correctly decode secret for signing, matching fits-service
    try:
        secret_bytes = base64.b64decode(settings.auth.secret_key)
    except Exception:
        secret_bytes = settings.auth.secret_key
        
    encoded_jwt = jwt.encode(to_encode, secret_bytes, algorithm=ALGORITHM)
    return encoded_jwt
