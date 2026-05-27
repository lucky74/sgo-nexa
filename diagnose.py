#!/usr/bin/env python3
"""
Jalankan: python diagnose.py 2>&1
Ini akan menunjukkan PERSIS di mana error terjadi saat load main.py
"""
import sys, os, traceback
os.chdir('/mnt/c/Users/user/Desktop/SGO_Nexa')
sys.path.insert(0, '.')

# Intercept semua exception
import builtins
_orig_import = builtins.__import__

errors = []

print("=== DIAGNOSA STARTUP ===\n")

# Step 1: Cek apakah ada error saat import
print("Step 1: Test import dependencies...")
deps = ['fastapi', 'aiogram', 'uvicorn', 'apscheduler', 'dotenv', 'PIL']
for dep in deps:
    try:
        __import__(dep.split('.')[0])
        print(f"  ✅ {dep}")
    except ImportError as e:
        print(f"  ❌ {dep}: {e}")

# Step 2: Load main.py dan tangkap error
print("\nStep 2: Load main.py...")
try:
    # Baca source
    src = open('main.py', encoding='utf-8-sig').read()
    
    # Compile dulu
    code = compile(src, 'main.py', 'exec')
    print("  ✅ Compile OK")
    
    # Execute dengan namespace baru
    ns = {'__name__': '__main__', '__file__': 'main.py'}
    
    # Patch agar tidak block
    import unittest.mock as mock
    
    exec(code, ns)
    
    app = ns.get('app')
    if app:
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        outlet_routes = [r for r in routes if 'outlet' in r]
        print(f"  ✅ App loaded: {len(routes)} routes, {len(outlet_routes)} outlet routes")
        
        # Cek route spesifik
        missing = []
        for r in ['/outlet/{outlet_id}/couriers', '/outlet/{outlet_id}/settings', '/outlet/{outlet_id}/vouchers']:
            if r not in outlet_routes:
                missing.append(r)
        
        if missing:
            print(f"  ❌ MISSING routes: {missing}")
        else:
            print(f"  ✅ Semua route penting ada")
    else:
        print("  ❌ app tidak ditemukan di namespace!")
        
except Exception as e:
    print(f"  ❌ ERROR: {e}")
    traceback.print_exc()

print("\n=== SELESAI ===")
