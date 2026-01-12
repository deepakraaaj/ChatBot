import asyncio
import httpx
import sys

BASE_URL = "http://localhost:8000"

async def verify():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        print("1. Checking Health (Public)...")
        try:
            resp = await client.get("/health")
            resp.raise_for_status()
            print(f"✅ Health OK: {resp.json()}")
        except Exception as e:
            print(f"❌ Health Failed: {e}")
            return

        print("\n2. Testing Public Access to Protected Route (Should Fail)...")
        try:
            resp = await client.post("/session/start")
            if resp.status_code == 401:
                print(f"✅ Correctly Blocked (401)")
            else:
                print(f"❌ Unexpected Status: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ Error: {e}")

        print("\n3. Login & Token (Requires user in DB)...")
        # Note: You need a user in DB.
        # email: admin@example.com / password: password
        # If not exists, this will fail.
        token = None
        try:
            resp = await client.post("/login", data={
                "username": "admin@example.com",
                "password": "password"
            })
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                print(f"✅ Login Success! Token: {token[:10]}...")
            else:
                print(f"❌ Login Failed: {resp.status_code} - {resp.text}")
                print("   (Ensure you have created a user in DB)")
        except Exception as e:
             print(f"❌ Login Error: {e}")

        if token:
             headers = {"Authorization": f"Bearer {token}"}
             
             print("\n4. Testing Protected Route with Token...")
             try:
                 resp = await client.post("/session/start", headers=headers)
                 if resp.status_code == 200:
                     print(f"✅ Session Started: {resp.json()}")
                 else:
                     print(f"❌ Failed: {resp.status_code} - {resp.text}")
             except Exception as e:
                 print(f"❌ Error: {e}")
             
             print("\n5. Testing Chat endpoint...")
             try:
                 resp = await client.post("/chat", headers=headers, json={
                     "session_id": "test_verification",
                     "message": "Hello secure world"
                 })
                 print(f"ℹ️ Chat Response Code: {resp.status_code}")
             except Exception as e:
                 print(f"❌ Chat Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except KeyboardInterrupt:
        pass
