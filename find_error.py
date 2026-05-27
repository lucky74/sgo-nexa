#!/usr/bin/env python3
"""
Cari di mana tepatnya error terjadi saat load main.py
Jalankan: python find_error.py 2>&1
"""
import sys, os, traceback
os.chdir('/mnt/c/Users/user/Desktop/SGO_Nexa')
sys.path.insert(0, '.')

src = open('main.py', encoding='utf-8-sig').read()
lines = src.split('\n')

# Cari semua route dan posisinya
import re
route_lines = []
for i, line in enumerate(lines, 1):
    if re.match(r'\s*@app\.(get|post)\(', line):
        route_lines.append((i, line.strip()))

print(f"Total route definitions: {len(route_lines)}")
print(f"\nRoute terakhir yang terdaftar di server: /outlet/{{outlet_id}}/sales-report")

# Cari baris sales-report
for i, (lineno, line) in enumerate(route_lines):
    if 'sales-report' in line:
        print(f"  -> Line {lineno}: {line}")
        print(f"\nRoute SETELAH sales-report:")
        for j in range(i+1, min(i+10, len(route_lines))):
            print(f"  Line {route_lines[j][0]}: {route_lines[j][1]}")
        break

# Cek kode antara sales-report dan route berikutnya
print("\n=== Kode antara sales-report dan route berikutnya ===")
in_range = False
count = 0
for i, line in enumerate(lines, 1):
    if 'outlet_id}/sales-report' in line:
        in_range = True
    if in_range:
        print(f"Line {i:4d}: {line}")
        count += 1
        if count > 5 and re.match(r'\s*@app\.(get|post)\(', line) and count > 3:
            break
        if count > 100:
            break
