import sys
import os

print("DEBUG: Starting detailed import check", flush=True)

print("DEBUG: Importing pydantic...", flush=True)
try:
    import pydantic
    print(f"DEBUG: pydantic imported. Version: {pydantic.VERSION}", flush=True)
except Exception as e:
    print(f"DEBUG: pydantic import failed: {e}", flush=True)

print("DEBUG: Importing aiohttp...", flush=True)
try:
    import aiohttp
    print(f"DEBUG: aiohttp imported. Version: {aiohttp.__version__}", flush=True)
except Exception as e:
    print(f"DEBUG: aiohttp import failed: {e}", flush=True)

print("DEBUG: Importing aiogram...", flush=True)
try:
    import aiogram
    print(f"DEBUG: aiogram imported. Version: {aiogram.__version__}", flush=True)
except Exception as e:
    print(f"DEBUG: aiogram import failed: {e}", flush=True)

print("DEBUG: Importing aiohttp_jinja2...", flush=True)
try:
    import aiohttp_jinja2
    print("DEBUG: aiohttp_jinja2 imported", flush=True)
except Exception as e:
    print(f"DEBUG: aiohttp_jinja2 import failed: {e}", flush=True)

print("DEBUG: Detailed import check finished", flush=True)
