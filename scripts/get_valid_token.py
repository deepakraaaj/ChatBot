import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.core.security import create_access_token

token = create_access_token(subject=1)
print(f"access_token: {token}")
