from app.core.security import verify_password, get_password_hash, create_access_token
import pytest
from app.core.settings import settings
from jose import jwt

@pytest.mark.skip(reason="Environment issue with bcrypt/passlib")
def test_password_hashing():
    password = "secret"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)

def test_access_token_creation():
    user_id = 123
    token = create_access_token(subject=user_id)
    import base64
    try:
        secret_bytes = base64.b64decode(settings.auth.secret_key)
    except:
        secret_bytes = settings.auth.secret_key
    payload = jwt.decode(token, secret_bytes, algorithms=["HS512"])
    assert payload["sub"] == str(user_id)
    assert "exp" in payload
