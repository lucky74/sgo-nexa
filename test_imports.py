print("Importing aiohttp", flush=True)
try:
    import aiohttp
    print(f"Aiohttp version: {aiohttp.__version__}", flush=True)
except Exception as e:
    print(f"Aiohttp error: {e}", flush=True)

print("Importing aiogram", flush=True)
try:
    import aiogram
    print(f"Aiogram version: {aiogram.__version__}", flush=True)
except Exception as e:
    print(f"Aiogram error: {e}", flush=True)
