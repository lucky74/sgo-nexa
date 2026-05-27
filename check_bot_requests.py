import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("API_TOKEN")

if not token:
    print("No token")
    exit(1)

print(f"Checking token: {token[:10]}...")
url = f"https://api.telegram.org/bot{token}/getMe"

try:
    resp = requests.get(url, timeout=10)
    print(f"Status: {resp.status_code}")
    print(resp.json())
except Exception as e:
    print(f"Error: {e}")
