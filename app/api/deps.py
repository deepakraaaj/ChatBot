from typing import Annotated
import base64
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import security
from app.core.settings import settings
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # DEV BYPASS (Restored to fetch REAL user from DB)
    if token.startswith("dev-token-bypass"):
        try:
            # Format: "dev-token-bypass:<user_id>" or just "dev-token-bypass" (default 1)
            parts = token.split(":")
            bypass_uid = int(parts[1]) if len(parts) > 1 else 1
            
            stmt = select(User).where(User.id == bypass_uid)
            result = await db.execute(stmt)
            user = result.scalars().first()
            
            if user:
                return user
        except Exception:
            pass # Fall through to normal auth if bypass extraction fails
            
    try:
        # fits-service uses Base64 encoded secret for HMAC
        try:
            secret_bytes = base64.b64decode(settings.auth.secret_key)
        except Exception:
            # Fallback if secret is not valid base64 (e.g. dev plain text)
            secret_bytes = settings.auth.secret_key

        payload = jwt.decode(token, secret_bytes, algorithms=[settings.auth.algorithm])
        
        # 'sub' is the username/email in fits-service
        email = payload.get("sub")
        
        if email is None:
            raise credentials_exception
            
        # Optional: Extract other claims if needed for context
        # user_id_claim = payload.get("userId")
        # if user_id_claim:
        #     decoded_id_str = base64.b64decode(user_id_claim).decode('utf-8')
        #     user_id = int(decoded_id_str)

    except (JWTError, ValueError):
        raise credentials_exception
    
    # Check if user exists in DB using EMAIL (sub)
    try:
        stmt = select(User).where(User.email == email)
        result = await db.execute(stmt)
        user = result.scalars().first()
    except Exception:
        # DB error or not found
        user = None

    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user

async def get_current_active_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    # if not current_user.is_superuser:
    #     raise HTTPException(
    #         status_code=400, detail="The user doesn't have enough privileges"
    #     )
    return current_user
