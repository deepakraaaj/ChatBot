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
            
        except Exception as e:
            print(f"DEBUG: Bypass logic error: {e}")
            pass # Fall through to normal auth if bypass extraction fails
            
    print(f"DEBUG: Validating token: {token[:20]}...")
    try:
        # fits-service uses Base64 encoded secret for HMAC
        try:
            print(f"DEBUG: Attempting to base64 decode secret key: {settings.auth.secret_key[:5]}...")
            secret_bytes = base64.b64decode(settings.auth.secret_key)
            print("DEBUG: Secret key decoded successfully.")
        except Exception as e:
            # Fallback if secret is not valid base64 (e.g. dev plain text)
            print(f"DEBUG: Failed to decode secret key as base64: {e}. Using raw string.")
            secret_bytes = settings.auth.secret_key

        print(f"DEBUG: Decoding JWT with algorithm: {settings.auth.algorithm}")
        payload = jwt.decode(token, secret_bytes, algorithms=[settings.auth.algorithm])
        print(f"DEBUG: Decoded payload: {payload}")
        
        # 'sub' is the username/email in fits-service
        email = payload.get("sub")
        print(f"DEBUG: Extracted email (sub): {email}")
        
        if email is None:
            print("DEBUG: Email claim is missing.")
            raise credentials_exception
            
        # Optional: Extract other claims if needed for context
        user_id = None
        user_id_claim = payload.get("userId")
        print(f"DEBUG: Extracted userId claim: {user_id_claim}")
        if user_id_claim:
            try:
                decoded_id_str = base64.b64decode(user_id_claim).decode('utf-8')
                user_id = int(decoded_id_str)
                print(f"DEBUG: Decoded userId: {user_id}")
            except Exception as e:
                 print(f"DEBUG: Failed to decode userId claim: {e}")

    except (JWTError, ValueError) as e:
        print(f"DEBUG: JWT Decode Error: {e}")
        raise credentials_exception
    
    # Check if user exists in DB using EMAIL (sub)
    try:
        if user_id:
             print(f"DEBUG: Looking up user by ID: {user_id}")
             stmt = select(User).where(User.id == user_id)
        else:
             print(f"DEBUG: Looking up user by Email: {email}")
             stmt = select(User).where(User.email == email)
             
        result = await db.execute(stmt)
        user = result.scalars().first()
        print(f"DEBUG: User lookup result: {user}")
    except Exception as e:
        print(f"DEBUG: DB Lookup Error: {e}")
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
