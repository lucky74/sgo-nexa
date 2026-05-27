#!/usr/bin/env python3
"""
Restore emoji yang rusak di main.py akibat fix_main_encoding2.py
yang mengganti \xe2\x80\x94 (em dash) dengan ' - '
padahal em dash itu bagian dari bytes emoji 4-byte.

Jalankan di WSL: python restore_emoji.py
"""

filepath = '/mnt/c/Users/user/Desktop/SGO_Nexa/main.py'

with open(filepath, 'rb') as f:
    raw = f.read()

print(f"File size: {len(raw):,} bytes")

# fix_main_encoding2.py mengganti:
# \xe2\x80\x94 -> b' - '
# Ini merusak emoji 4-byte yang strukturnya: \xf0\x9f\xXX\xYY
# karena \x94 adalah byte terakhir dari beberapa emoji

# Restore emoji yang rusak:
# Format: (bytes_rusak, bytes_benar)
RESTORES = [
    # 🔔 bell: f0 9f 94 94 -> tapi \x94 diganti jadi ' - '
    # f0 9f 94 ' - ' -> f0 9f 94 94
    (b'\xf0\x9f\x94 - ', b'\xf0\x9f\x94\x94'),  # 🔔
    # 🔕: f0 9f 94 95
    (b'\xf0\x9f\x94 - \x95', b'\xf0\x9f\x94\x95'),
    # Pola umum: f0 9f XX ' - ' YY -> cek konteks
]

# Cara lebih aman: cari semua ' - ' yang ada di tengah sequence emoji
import re

# Cari pattern: byte emoji (f0 9f XX) diikuti ' - ' 
# yang seharusnya adalah byte ke-4 dari emoji
count_fixed = 0

# Scan manual
i = 0
result = bytearray()
while i < len(raw):
    # Cek apakah ini sequence ' - ' yang menggantikan byte emoji
    if raw[i:i+3] == b' - ' and i >= 3:
        # Cek apakah 3 byte sebelumnya adalah awal emoji 4-byte
        prev3 = bytes(result[-3:]) if len(result) >= 3 else b''
        if len(prev3) == 3 and prev3[0] == 0xf0 and prev3[1] == 0x9f:
            # Ini kemungkinan byte ke-4 emoji yang hilang
            # Tapi kita tidak tahu byte aslinya...
            # Skip untuk sekarang
            pass
    result.append(raw[i])
    i += 1

# Pendekatan berbeda: lihat konteks di sekitar ' - '
print("\n=== Mencari ' - ' yang mencurigakan ===")
idx = 0
suspicious = []
while True:
    idx = raw.find(b' - ', idx)
    if idx == -1:
        break
    context = raw[max(0,idx-5):idx+8]
    # Cek apakah ada byte non-ASCII di sekitarnya
    has_high = any(b > 0x7f for b in context[:5]) or any(b > 0x7f for b in context[3:])
    if has_high:
        suspicious.append((idx, context))
    idx += 3

print(f"Found {len(suspicious)} suspicious ' - ' patterns")
for pos, ctx in suspicious[:10]:
    print(f"  pos {pos}: {ctx.hex()} = {ctx}")

print("\nFile tidak diubah - perlu analisis lebih lanjut")
print("Emoji yang hilang kemungkinan perlu diperbaiki manual di main.py")
